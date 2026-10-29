from datetime import date, datetime, time, timedelta
from decimal import Decimal
from io import StringIO
from unittest import mock
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from .lembretes import (
    agendamentos_para_lembrar,
    enviar_lembrete,
    gerar_token,
    ler_token,
    link_agendamento,
)
from .models import Agendamento, Cliente, HorarioFuncionamento, Negocio, Servico
from .whatsapp import MemoriaBackend

SP = ZoneInfo('America/Sao_Paulo')
# Segunda-feira, 10h
AGORA = datetime(2026, 10, 19, 10, 0, tzinfo=SP)
TERCA = date(2026, 10, 20)


def em(dia, hora, minuto=0):
    return datetime.combine(dia, time(hora, minuto), tzinfo=SP)


@override_settings(
    WHATSAPP_BACKEND='agenda.whatsapp.MemoriaBackend', SITE_URL='https://exemplo.com.br'
)
class LembreteTestCase(TestCase):
    def setUp(self):
        relogio = mock.patch('django.utils.timezone.now', return_value=AGORA)
        relogio.start()
        self.addCleanup(relogio.stop)
        MemoriaBackend.enviadas.clear()
        self.addCleanup(MemoriaBackend.enviadas.clear)
        dono = get_user_model().objects.create_user('dono', password='senha-teste')
        self.negocio = Negocio.objects.create(
            dono=dono, nome='Barbearia do Zé', slug='ze', whatsapp='5511999998888'
        )
        self.corte = Servico.objects.create(
            negocio=self.negocio, nome='Corte', duracao_minutos=30, preco=Decimal('40')
        )
        self.cliente = Cliente.objects.create(
            negocio=self.negocio, nome='Ana', whatsapp='5511966665555'
        )

    def agendar(self, inicio, **extra):
        return Agendamento.objects.create(
            negocio=self.negocio, servico=self.corte, cliente=self.cliente, inicio=inicio, **extra
        )


class QuemRecebeLembreteTests(LembreteTestCase):
    def test_agendamentos_das_proximas_24h(self):
        dentro = self.agendar(em(TERCA, 9))
        no_limite = self.agendar(em(TERCA, 10))
        self.agendar(em(TERCA, 10, 30))  # mais de 24h
        self.assertEqual(list(agendamentos_para_lembrar()), [dentro, no_limite])

    def test_inclui_confirmados_e_ignora_cancelados(self):
        confirmado = self.agendar(em(TERCA, 9), status=Agendamento.Status.CONFIRMADO)
        self.agendar(em(TERCA, 9, 30), status=Agendamento.Status.CANCELADO)
        self.assertEqual(list(agendamentos_para_lembrar()), [confirmado])

    def test_ignora_os_que_ja_receberam_lembrete(self):
        self.agendar(em(TERCA, 9), lembrete_enviado_em=AGORA - timedelta(hours=1))
        self.assertEqual(list(agendamentos_para_lembrar()), [])

    def test_ignora_horarios_que_ja_comecaram(self):
        self.agendar(AGORA)
        self.agendar(AGORA - timedelta(hours=1))
        self.assertEqual(list(agendamentos_para_lembrar()), [])


class EnviarLembreteTests(LembreteTestCase):
    def test_envia_para_o_whatsapp_do_cliente_e_marca_como_enviado(self):
        agendamento = self.agendar(em(TERCA, 9))
        self.assertTrue(enviar_lembrete(agendamento))

        [(numero, texto)] = MemoriaBackend.enviadas
        self.assertEqual(numero, '5511966665555')
        self.assertIn('Olá, Ana!', texto)
        self.assertIn('Barbearia do Zé', texto)
        self.assertIn('Corte, terça-feira, 20/10 às 09:00', texto)
        self.assertIn(link_agendamento(agendamento), texto)
        agendamento.refresh_from_db()
        self.assertEqual(agendamento.lembrete_enviado_em, AGORA)

    def test_nao_envia_duas_vezes(self):
        agendamento = self.agendar(em(TERCA, 9))
        enviar_lembrete(agendamento)
        # Outra execução com o objeto antigo em memória (ex: dois crons ao mesmo tempo)
        copia = Agendamento.objects.get(pk=agendamento.pk)
        copia.lembrete_enviado_em = None
        self.assertFalse(enviar_lembrete(copia))
        self.assertEqual(len(MemoriaBackend.enviadas), 1)

    def test_nao_envia_se_foi_cancelado_depois_de_listado(self):
        agendamento = self.agendar(em(TERCA, 9))
        [listado] = agendamentos_para_lembrar()
        Agendamento.objects.filter(pk=agendamento.pk).update(status=Agendamento.Status.CANCELADO)
        self.assertFalse(enviar_lembrete(listado))
        self.assertEqual(MemoriaBackend.enviadas, [])

    def test_falha_no_envio_desfaz_a_marcacao(self):
        agendamento = self.agendar(em(TERCA, 9))
        with mock.patch.object(MemoriaBackend, 'enviar', side_effect=ConnectionError):
            with self.assertRaises(ConnectionError):
                enviar_lembrete(agendamento)
        agendamento.refresh_from_db()
        self.assertIsNone(agendamento.lembrete_enviado_em)

    def test_link_absoluto_com_token(self):
        agendamento = self.agendar(em(TERCA, 9))
        self.assertEqual(
            link_agendamento(agendamento),
            'https://exemplo.com.br'
            + reverse('agenda:gerenciar_agendamento', args=['ze', gerar_token(agendamento)]),
        )

    def test_token_invalido(self):
        agendamento = self.agendar(em(TERCA, 9))
        self.assertEqual(ler_token(gerar_token(agendamento)), agendamento.pk)
        self.assertIsNone(ler_token('MQ:assinatura-falsa'))
        self.assertIsNone(ler_token(str(agendamento.pk)))


class ComandoEnviarLembretesTests(LembreteTestCase):
    def rodar(self):
        saida, erros = StringIO(), StringIO()
        call_command('enviar_lembretes', stdout=saida, stderr=erros)
        return saida.getvalue(), erros.getvalue()

    def test_envia_os_lembretes_pendentes(self):
        self.agendar(em(TERCA, 9))
        self.agendar(em(TERCA, 9, 30))
        self.agendar(em(TERCA, 11))  # fora da janela
        saida, _ = self.rodar()
        self.assertIn('Lembretes enviados: 2. Falhas: 0.', saida)
        self.assertEqual(len(MemoriaBackend.enviadas), 2)

    def test_rodar_de_novo_nao_reenvia(self):
        self.agendar(em(TERCA, 9))
        self.rodar()
        saida, _ = self.rodar()
        self.assertIn('Lembretes enviados: 0.', saida)
        self.assertEqual(len(MemoriaBackend.enviadas), 1)

    def test_uma_falha_nao_impede_os_outros(self):
        primeiro = self.agendar(em(TERCA, 9))
        self.agendar(em(TERCA, 9, 30))
        original = MemoriaBackend.enviar

        def enviar(backend, numero, texto):
            if '09:00' in texto:
                raise ConnectionError('fora do ar')
            original(backend, numero, texto)

        with mock.patch.object(MemoriaBackend, 'enviar', enviar):
            with self.assertLogs('agenda.management', 'ERROR') as logs:
                saida, _ = self.rodar()
        self.assertIn('Lembretes enviados: 1. Falhas: 1.', saida)
        [registro] = logs.records
        self.assertEqual(registro.getMessage(), f'Falha no lembrete do agendamento {primeiro.pk}')
        self.assertIsInstance(registro.exc_info[1], ConnectionError)
        primeiro.refresh_from_db()
        self.assertIsNone(primeiro.lembrete_enviado_em)


class GerenciarAgendamentoTests(LembreteTestCase):
    def setUp(self):
        super().setUp()
        self.agendamento = self.agendar(em(TERCA, 9))
        self.url = reverse(
            'agenda:gerenciar_agendamento', args=['ze', gerar_token(self.agendamento)]
        )

    def status(self):
        self.agendamento.refresh_from_db()
        return self.agendamento.status

    def test_get_mostra_o_agendamento_sem_alterar(self):
        resposta = self.client.get(self.url)
        self.assertContains(resposta, 'Corte')
        self.assertContains(resposta, 'Confirmar presença')
        self.assertContains(resposta, 'Cancelar horário')
        self.assertEqual(self.status(), Agendamento.Status.AGENDADO)

    def test_confirmar(self):
        resposta = self.client.post(self.url, {'acao': 'confirmar'})
        self.assertRedirects(resposta, self.url)
        self.assertEqual(self.status(), Agendamento.Status.CONFIRMADO)
        self.assertNotContains(self.client.get(self.url), 'Confirmar presença')
        self.assertEqual(MemoriaBackend.enviadas, [])

    def test_cancelar_avisa_o_dono(self):
        self.client.post(self.url, {'acao': 'cancelar'})
        self.assertEqual(self.status(), Agendamento.Status.CANCELADO)
        [(numero, texto)] = MemoriaBackend.enviadas
        self.assertEqual(numero, '5511999998888')
        self.assertIn('Agendamento cancelado pelo cliente: Ana (5511966665555)', texto)

    def test_confirmado_ainda_pode_cancelar(self):
        self.agendamento.status = Agendamento.Status.CONFIRMADO
        self.agendamento.save()
        self.client.post(self.url, {'acao': 'cancelar'})
        self.assertEqual(self.status(), Agendamento.Status.CANCELADO)

    def test_cancelado_nao_volta(self):
        self.agendamento.status = Agendamento.Status.CANCELADO
        self.agendamento.save()
        resposta = self.client.post(self.url, {'acao': 'confirmar'}, follow=True)
        self.assertEqual(self.status(), Agendamento.Status.CANCELADO)
        self.assertContains(resposta, 'Este horário foi cancelado.')
        self.assertNotContains(resposta, 'Cancelar horário')

    def post_com_cancelamento_concorrente(self, acao):
        """A view lê o agendamento como ativo, mas outra requisição o cancela antes do update."""
        original = Agendamento.objects.select_related

        def ler_e_cancelar(*args):
            consulta = original(*args)
            list(consulta)  # avalia a leitura da view antes do cancelamento
            Agendamento.objects.filter(pk=self.agendamento.pk).update(
                status=Agendamento.Status.CANCELADO
            )
            return consulta

        with mock.patch.object(Agendamento.objects, 'select_related', ler_e_cancelar):
            self.client.post(self.url, {'acao': acao})

    def test_cancelamento_concorrente_avisa_o_dono_uma_vez_so(self):
        self.post_com_cancelamento_concorrente('cancelar')
        self.assertEqual(self.status(), Agendamento.Status.CANCELADO)
        self.assertEqual(MemoriaBackend.enviadas, [])

    def test_confirmar_nao_desfaz_cancelamento_concorrente(self):
        self.post_com_cancelamento_concorrente('confirmar')
        self.assertEqual(self.status(), Agendamento.Status.CANCELADO)

    def test_horario_que_ja_passou_nao_pode_ser_alterado(self):
        with mock.patch('django.utils.timezone.now', return_value=em(TERCA, 9, 1)):
            resposta = self.client.post(self.url, {'acao': 'cancelar'}, follow=True)
        self.assertEqual(self.status(), Agendamento.Status.AGENDADO)
        self.assertContains(resposta, 'Este horário já passou.')

    def test_token_invalido_da_404(self):
        url = reverse('agenda:gerenciar_agendamento', args=['ze', 'MQ:falso'])
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_token_de_outro_negocio_da_404(self):
        Negocio.objects.create(
            dono=self.negocio.dono, nome='Outro', slug='outro', whatsapp='5511911112222'
        )
        url = reverse(
            'agenda:gerenciar_agendamento', args=['outro', gerar_token(self.agendamento)]
        )
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_id_puro_na_url_nao_funciona(self):
        url = reverse('agenda:gerenciar_agendamento', args=['ze', str(self.agendamento.pk)])
        self.assertEqual(self.client.get(url).status_code, 404)


class AvisoNovoAgendamentoTests(LembreteTestCase):
    def setUp(self):
        super().setUp()
        HorarioFuncionamento.objects.create(
            negocio=self.negocio,
            dia_semana=HorarioFuncionamento.DiaSemana.TERCA,
            abertura=time(9),
            fechamento=time(10),
        )
        self.url = reverse('agenda:confirmar_agendamento', args=['ze', self.corte.pk])
        self.dados = {'inicio': '2026-10-20T09:30', 'nome': 'João', 'whatsapp': '11988887777'}

    def test_dono_recebe_aviso_de_novo_agendamento(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(self.url, self.dados)
        [(numero, texto)] = MemoriaBackend.enviadas
        self.assertEqual(numero, '5511999998888')
        self.assertEqual(
            texto, 'Novo agendamento: João (5511988887777) – Corte, terça-feira, 20/10 às 09:30.'
        )

    def test_falha_no_aviso_nao_impede_o_agendamento(self):
        with mock.patch.object(MemoriaBackend, 'enviar', side_effect=ConnectionError):
            with self.assertLogs('agenda.lembretes', 'ERROR'):
                with self.captureOnCommitCallbacks(execute=True):
                    resposta = self.client.post(self.url, self.dados)
        self.assertRedirects(resposta, reverse('agenda:agendamento_concluido', args=['ze']))
        self.assertEqual(Agendamento.objects.count(), 1)

    def test_horario_ocupado_nao_avisa(self):
        self.agendar(em(TERCA, 9, 30))
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(self.url, self.dados)
        self.assertEqual(MemoriaBackend.enviadas, [])
