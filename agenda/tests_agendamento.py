from datetime import date, datetime, time
from decimal import Decimal
from unittest import mock
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .forms import normalizar_whatsapp
from .models import Agendamento, Bloqueio, Cliente, HorarioFuncionamento, Negocio, Servico

SP = ZoneInfo('America/Sao_Paulo')
# Segunda-feira, antes de abrir
AGORA = datetime(2026, 10, 19, 8, 0, tzinfo=SP)


def em(dia, hora, minuto=0):
    return datetime.combine(dia, time(hora, minuto), tzinfo=SP)


SEGUNDA = date(2026, 10, 19)
TERCA = date(2026, 10, 20)


class FluxoAgendamentoTestCase(TestCase):
    def setUp(self):
        relogio = mock.patch('django.utils.timezone.now', return_value=AGORA)
        relogio.start()
        self.addCleanup(relogio.stop)
        dono = get_user_model().objects.create_user('dono', password='senha-teste')
        self.negocio = Negocio.objects.create(
            dono=dono, nome='Barbearia do Zé', slug='ze', whatsapp='5511999998888'
        )
        self.corte = Servico.objects.create(
            negocio=self.negocio, nome='Corte', duracao_minutos=30, preco=Decimal('40')
        )
        for dia in (HorarioFuncionamento.DiaSemana.SEGUNDA, HorarioFuncionamento.DiaSemana.TERCA):
            HorarioFuncionamento.objects.create(
                negocio=self.negocio, dia_semana=dia, abertura=time(9), fechamento=time(10)
            )
        self.url_horarios = reverse('agenda:escolher_horario', args=['ze', self.corte.pk])
        self.url_confirmar = reverse('agenda:confirmar_agendamento', args=['ze', self.corte.pk])

    def agendar_outro(self, inicio):
        cliente = Cliente.objects.create(negocio=self.negocio, nome='Ana', whatsapp='5511966665555')
        return Agendamento.objects.create(
            negocio=self.negocio, servico=self.corte, cliente=cliente, inicio=inicio
        )

    def dados(self, **extra):
        return {'inicio': '2026-10-20T09:30', 'nome': 'João', 'whatsapp': '(11) 98888-7777', **extra}


class PaginaComBotaoAgendarTests(FluxoAgendamentoTestCase):
    def test_pagina_publica_tem_link_para_agendar(self):
        resposta = self.client.get(reverse('agenda:pagina_negocio', args=['ze']))
        self.assertContains(resposta, self.url_horarios)


class EscolherHorarioTests(FluxoAgendamentoTestCase):
    def test_lista_so_dias_de_atendimento_nos_proximos_14_dias(self):
        resposta = self.client.get(self.url_horarios)
        self.assertEqual(
            resposta.context['dias'],
            [SEGUNDA, TERCA, date(2026, 10, 26), date(2026, 10, 27)],
        )

    def test_sem_dia_escolhido_mostra_o_primeiro(self):
        resposta = self.client.get(self.url_horarios)
        self.assertEqual(resposta.context['dia'], SEGUNDA)
        self.assertEqual(resposta.context['horarios'], [em(SEGUNDA, 9), em(SEGUNDA, 9, 30)])

    def test_mostra_horarios_do_dia_escolhido(self):
        self.agendar_outro(em(TERCA, 9))
        resposta = self.client.get(self.url_horarios, {'dia': '2026-10-20'})
        self.assertEqual(resposta.context['horarios'], [em(TERCA, 9, 30)])
        self.assertContains(resposta, f'{self.url_confirmar}?inicio=2026-10-20T09:30')
        self.assertNotContains(resposta, 'inicio=2026-10-20T09:00')

    def test_dia_invalido_ou_fora_da_janela_volta_para_o_primeiro(self):
        for dia in ['abc', '2026-10-21', '2026-11-30', '2026-10-12']:
            with self.subTest(dia=dia):
                resposta = self.client.get(self.url_horarios, {'dia': dia})
                self.assertEqual(resposta.context['dia'], SEGUNDA)

    def test_requisicao_htmx_devolve_so_o_trecho(self):
        resposta = self.client.get(self.url_horarios, {'dia': '2026-10-20'}, HTTP_HX_REQUEST='true')
        self.assertContains(resposta, 'Horários em')
        self.assertNotContains(resposta, '<html')

    def test_pagina_completa_sem_htmx(self):
        self.assertContains(self.client.get(self.url_horarios), '<html')

    def test_dia_lotado_mostra_aviso(self):
        Bloqueio.objects.create(negocio=self.negocio, inicio=em(SEGUNDA, 0), fim=em(TERCA, 0))
        self.assertContains(self.client.get(self.url_horarios), 'Nenhum horário livre')

    def test_sem_horario_de_funcionamento(self):
        self.negocio.horarios.all().delete()
        self.assertContains(self.client.get(self.url_horarios), 'Não há dias disponíveis')

    def test_servico_inativo_retorna_404(self):
        self.corte.ativo = False
        self.corte.save()
        self.assertEqual(self.client.get(self.url_horarios).status_code, 404)

    def test_servico_de_outro_negocio_retorna_404(self):
        dono = get_user_model().objects.create_user('outro', password='senha-teste')
        outro = Negocio.objects.create(dono=dono, nome='Outra', slug='outra', whatsapp='5511977776666')
        url = reverse('agenda:escolher_horario', args=['outra', self.corte.pk])
        self.assertEqual(self.client.get(url).status_code, 404)


class ConfirmarAgendamentoTests(FluxoAgendamentoTestCase):
    def test_horario_livre_mostra_formulario(self):
        resposta = self.client.get(self.url_confirmar, {'inicio': '2026-10-20T09:30'})
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.context['inicio'], em(TERCA, 9, 30))
        self.assertContains(resposta, 'name="whatsapp"')

    def test_horario_ocupado_volta_para_escolha(self):
        self.agendar_outro(em(TERCA, 9, 30))
        resposta = self.client.get(self.url_confirmar, {'inicio': '2026-10-20T09:30'})
        self.assertRedirects(resposta, self.url_horarios)

    def test_horario_invalido_volta_para_escolha(self):
        for inicio in ['', 'abc', '2026-10-20T09:10', '2026-10-19T07:00']:
            with self.subTest(inicio=inicio):
                resposta = self.client.get(self.url_confirmar, {'inicio': inicio})
                self.assertRedirects(resposta, self.url_horarios)

    def test_agendar_cria_cliente_e_agendamento(self):
        resposta = self.client.post(self.url_confirmar, self.dados())
        self.assertRedirects(resposta, reverse('agenda:agendamento_concluido', args=['ze']))
        agendamento = Agendamento.objects.get()
        self.assertEqual(agendamento.inicio, em(TERCA, 9, 30))
        self.assertEqual(agendamento.fim, em(TERCA, 10))
        self.assertEqual(agendamento.servico, self.corte)
        self.assertEqual(agendamento.status, Agendamento.Status.AGENDADO)
        self.assertEqual(agendamento.cliente.nome, 'João')
        self.assertEqual(agendamento.cliente.whatsapp, '5511988887777')
        self.assertEqual(agendamento.cliente.negocio, self.negocio)

    def test_cliente_existente_e_reaproveitado_pelo_whatsapp(self):
        Cliente.objects.create(negocio=self.negocio, nome='Joao', whatsapp='5511988887777')
        self.client.post(self.url_confirmar, self.dados(nome='João Silva'))
        cliente = Cliente.objects.get(negocio=self.negocio)
        self.assertEqual(cliente.nome, 'João Silva')
        self.assertEqual(cliente.agendamentos.count(), 1)

    def test_whatsapp_invalido_mostra_erro_e_nao_cria(self):
        resposta = self.client.post(self.url_confirmar, self.dados(whatsapp='1234'))
        self.assertEqual(resposta.status_code, 200)
        self.assertFormError(resposta.context['form'], 'whatsapp', [
            'Informe o WhatsApp só com dígitos, com DDI e DDD (ex: 5511999998888).'
        ])
        self.assertFalse(Agendamento.objects.exists())
        self.assertFalse(Cliente.objects.exists())

    def test_nome_vazio_mostra_erro(self):
        resposta = self.client.post(self.url_confirmar, self.dados(nome='   '))
        self.assertEqual(resposta.status_code, 200)
        self.assertIn('nome', resposta.context['form'].errors)
        self.assertFalse(Agendamento.objects.exists())

    def test_horario_ocupado_entre_a_escolha_e_o_envio(self):
        self.agendar_outro(em(TERCA, 9, 30))
        resposta = self.client.post(self.url_confirmar, self.dados())
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'Esse horário acabou de ser ocupado')
        self.assertEqual(Agendamento.objects.count(), 1)
        self.assertFalse(Cliente.objects.filter(whatsapp='5511988887777').exists())

    def test_horario_passado_nao_agenda(self):
        resposta = self.client.post(self.url_confirmar, self.dados(inicio='2026-10-19T07:30'))
        self.assertContains(resposta, 'Esse horário acabou de ser ocupado')
        self.assertFalse(Agendamento.objects.exists())

    def test_inicio_adulterado_volta_para_escolha(self):
        resposta = self.client.post(self.url_confirmar, self.dados(inicio='abc'))
        self.assertRedirects(resposta, self.url_horarios)
        self.assertFalse(Agendamento.objects.exists())

    def test_get_e_post_usam_o_mesmo_horario(self):
        resposta = self.client.get(self.url_confirmar, {'inicio': '2026-10-20T09:30'})
        inicio_no_form = resposta.context['form']['inicio'].value()
        self.client.post(self.url_confirmar, self.dados(inicio=inicio_no_form))
        self.assertEqual(Agendamento.objects.get().inicio, em(TERCA, 9, 30))


class AgendamentoConcluidoTests(FluxoAgendamentoTestCase):
    def test_mostra_resumo_apos_agendar(self):
        resposta = self.client.post(self.url_confirmar, self.dados(), follow=True)
        self.assertContains(resposta, 'Agendamento feito!')
        self.assertContains(resposta, 'Corte')
        self.assertContains(resposta, '20/10/2026')
        self.assertContains(resposta, '09:30')

    def test_sem_agendamento_na_sessao_volta_para_pagina(self):
        resposta = self.client.get(reverse('agenda:agendamento_concluido', args=['ze']))
        self.assertRedirects(resposta, reverse('agenda:pagina_negocio', args=['ze']))

    def test_nao_mostra_agendamento_na_pagina_de_outro_negocio(self):
        dono = get_user_model().objects.create_user('outro', password='senha-teste')
        Negocio.objects.create(dono=dono, nome='Outra', slug='outra', whatsapp='5511977776666')
        self.client.post(self.url_confirmar, self.dados())
        resposta = self.client.get(reverse('agenda:agendamento_concluido', args=['outra']))
        self.assertRedirects(resposta, reverse('agenda:pagina_negocio', args=['outra']))


class NormalizarWhatsappTests(TestCase):
    def test_formatos(self):
        casos = {
            '(11) 98888-7777': '5511988887777',
            '11988887777': '5511988887777',
            '1133334444': '551133334444',
            '+55 11 98888-7777': '5511988887777',
            '5511988887777': '5511988887777',
            '1234': '1234',
        }
        for entrada, esperado in casos.items():
            with self.subTest(entrada=entrada):
                self.assertEqual(normalizar_whatsapp(entrada), esperado)
