from datetime import date, datetime, time
from decimal import Decimal
from unittest import mock
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Agendamento, Bloqueio, Cliente, HorarioFuncionamento, Negocio, Servico

SP = ZoneInfo('America/Sao_Paulo')
HOJE = date(2026, 10, 19)
AGORA = datetime(2026, 10, 19, 8, 0, tzinfo=SP)


def em(dia, hora, minuto=0):
    return datetime.combine(dia, time(hora, minuto), tzinfo=SP)


class PainelTestCase(TestCase):
    def setUp(self):
        relogio = mock.patch('django.utils.timezone.now', return_value=AGORA)
        relogio.start()
        self.addCleanup(relogio.stop)

        User = get_user_model()
        self.dono = User.objects.create_user('dono', password='senha-teste')
        self.negocio = Negocio.objects.create(
            dono=self.dono, nome='Barbearia do Zé', slug='ze', whatsapp='5511999998888'
        )
        self.corte = Servico.objects.create(
            negocio=self.negocio, nome='Corte', duracao_minutos=30, preco=Decimal('40')
        )
        self.cliente = Cliente.objects.create(
            negocio=self.negocio, nome='João', whatsapp='5511988887777'
        )

        outro_dono = User.objects.create_user('outro', password='senha-teste')
        self.outro = Negocio.objects.create(
            dono=outro_dono, nome='Outra', slug='outra', whatsapp='5511977776666'
        )
        self.servico_outro = Servico.objects.create(
            negocio=self.outro, nome='Sobrancelha', duracao_minutos=15, preco=Decimal('10')
        )
        self.cliente_outro = Cliente.objects.create(
            negocio=self.outro, nome='Ana', whatsapp='5511966665555'
        )

        self.client.force_login(self.dono)

    def agendar(self, inicio, negocio=None, status=Agendamento.Status.AGENDADO):
        outro = negocio == self.outro
        return Agendamento.objects.create(
            negocio=negocio or self.negocio,
            servico=self.servico_outro if outro else self.corte,
            cliente=self.cliente_outro if outro else self.cliente,
            inicio=inicio,
            status=status,
        )


class AcessoTests(PainelTestCase):
    def test_sem_login_vai_para_o_login(self):
        self.client.logout()
        for nome in ['agenda', 'servicos', 'horarios', 'bloqueios', 'servico_novo']:
            with self.subTest(nome=nome):
                url = reverse(f'painel:{nome}')
                self.assertRedirects(
                    self.client.get(url), f"{reverse('login')}?next={url}", fetch_redirect_response=False
                )

    def test_login_leva_ao_painel(self):
        self.client.logout()
        self.assertContains(self.client.get(reverse('login')), 'Entrar no painel')
        resposta = self.client.post(
            reverse('login'), {'username': 'dono', 'password': 'senha-teste'}
        )
        self.assertRedirects(resposta, reverse('painel:agenda'))

    def test_login_com_senha_errada(self):
        self.client.logout()
        resposta = self.client.post(reverse('login'), {'username': 'dono', 'password': 'errada'})
        self.assertContains(resposta, 'Usuário ou senha incorretos')

    def test_sair(self):
        resposta = self.client.post(reverse('logout'))
        self.assertRedirects(resposta, reverse('login'))
        self.assertEqual(self.client.get(reverse('painel:agenda')).status_code, 302)

    def test_usuario_sem_negocio(self):
        sem = get_user_model().objects.create_user('sem', password='senha-teste')
        self.client.force_login(sem)
        resposta = self.client.get(reverse('painel:agenda'))
        self.assertEqual(resposta.status_code, 403)
        self.assertContains(resposta, 'Nenhum negócio cadastrado', status_code=403)


class AgendaDoDiaTests(PainelTestCase):
    def test_mostra_agendamentos_de_hoje(self):
        self.agendar(em(HOJE, 9))
        self.agendar(em(HOJE, 10), status=Agendamento.Status.CANCELADO)
        self.agendar(em(date(2026, 10, 20), 9))  # amanhã
        self.agendar(em(HOJE, 9, 30), negocio=self.outro)
        resposta = self.client.get(reverse('painel:agenda'))
        self.assertEqual(resposta.context['dia'], HOJE)
        self.assertEqual(
            [ag.inicio for ag in resposta.context['agendamentos']], [em(HOJE, 9), em(HOJE, 10)]
        )
        self.assertContains(resposta, 'João')
        self.assertContains(resposta, 'https://wa.me/5511988887777')
        self.assertNotContains(resposta, 'Ana')

    def test_navega_para_outro_dia(self):
        self.agendar(em(date(2026, 10, 20), 9))
        resposta = self.client.get(reverse('painel:agenda'), {'dia': '2026-10-20'})
        self.assertEqual(len(resposta.context['agendamentos']), 1)
        self.assertContains(resposta, '?dia=2026-10-21')
        self.assertContains(resposta, '?dia=2026-10-19')

    def test_dia_invalido_mostra_hoje(self):
        resposta = self.client.get(reverse('painel:agenda'), {'dia': 'abc'})
        self.assertEqual(resposta.context['dia'], HOJE)

    def test_agendamento_perto_da_meia_noite_fica_no_dia_certo(self):
        self.agendar(em(HOJE, 23, 30))
        resposta = self.client.get(reverse('painel:agenda'), {'dia': '2026-10-20'})
        self.assertEqual(len(resposta.context['agendamentos']), 0)
        resposta = self.client.get(reverse('painel:agenda'))
        self.assertEqual(len(resposta.context['agendamentos']), 1)

    def test_mostra_bloqueios_do_dia(self):
        Bloqueio.objects.create(
            negocio=self.negocio, inicio=em(HOJE, 12), fim=em(HOJE, 14), motivo='Dentista'
        )
        self.assertContains(self.client.get(reverse('painel:agenda')), 'Dentista')

    def test_dia_vazio(self):
        self.assertContains(self.client.get(reverse('painel:agenda')), 'Nenhum agendamento')


class AlterarStatusTests(PainelTestCase):
    def url(self, agendamento):
        return reverse('painel:alterar_status', args=[agendamento.pk])

    def test_confirmar(self):
        ag = self.agendar(em(HOJE, 9))
        resposta = self.client.post(self.url(ag), {'status': 'confirmado'})
        self.assertRedirects(resposta, f"{reverse('painel:agenda')}?dia=2026-10-19")
        ag.refresh_from_db()
        self.assertEqual(ag.status, Agendamento.Status.CONFIRMADO)

    def test_cancelar_libera_o_horario(self):
        ag = self.agendar(em(HOJE, 9))
        self.client.post(self.url(ag), {'status': 'cancelado'})
        ag.refresh_from_db()
        self.assertEqual(ag.status, Agendamento.Status.CANCELADO)

    def test_cancelado_nao_volta_a_ser_confirmado(self):
        ag = self.agendar(em(HOJE, 9), status=Agendamento.Status.CANCELADO)
        resposta = self.client.post(self.url(ag), {'status': 'confirmado'}, follow=True)
        self.assertContains(resposta, 'já foi cancelado')
        ag.refresh_from_db()
        self.assertEqual(ag.status, Agendamento.Status.CANCELADO)

    def test_status_invalido(self):
        ag = self.agendar(em(HOJE, 9))
        self.assertEqual(self.client.post(self.url(ag), {'status': 'agendado'}).status_code, 400)

    def test_agendamento_de_outro_negocio_retorna_404(self):
        ag = self.agendar(em(HOJE, 9), negocio=self.outro)
        self.assertEqual(self.client.post(self.url(ag), {'status': 'cancelado'}).status_code, 404)
        ag.refresh_from_db()
        self.assertEqual(ag.status, Agendamento.Status.AGENDADO)

    def test_so_aceita_post(self):
        ag = self.agendar(em(HOJE, 9))
        self.assertEqual(self.client.get(self.url(ag)).status_code, 405)


class ServicosTests(PainelTestCase):
    def test_lista_inclui_inativos_e_nao_mostra_de_outro_negocio(self):
        Servico.objects.create(
            negocio=self.negocio, nome='Luzes', duracao_minutos=60, preco=90, ativo=False
        )
        resposta = self.client.get(reverse('painel:servicos'))
        self.assertContains(resposta, 'Luzes (inativo)')
        self.assertNotContains(resposta, 'Sobrancelha')

    def test_criar(self):
        resposta = self.client.post(
            reverse('painel:servico_novo'),
            {'nome': 'Barba', 'duracao_minutos': 20, 'preco': '30,00', 'ativo': 'on'},
        )
        self.assertRedirects(resposta, reverse('painel:servicos'))
        barba = Servico.objects.get(nome='Barba')
        self.assertEqual(barba.negocio, self.negocio)
        self.assertEqual(barba.preco, Decimal('30.00'))

    def test_editar_e_desativar(self):
        url = reverse('painel:servico_editar', args=[self.corte.pk])
        resposta = self.client.get(url)
        self.assertContains(resposta, 'Editar Corte')
        self.assertContains(resposta, 'value="40,00"')
        self.client.post(url, {'nome': 'Corte', 'duracao_minutos': 40, 'preco': '45'})
        self.corte.refresh_from_db()
        self.assertEqual(self.corte.duracao_minutos, 40)
        self.assertFalse(self.corte.ativo)

    def test_dados_invalidos(self):
        resposta = self.client.post(
            reverse('painel:servico_novo'), {'nome': 'X', 'duracao_minutos': 2, 'preco': '-1'}
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertIn('duracao_minutos', resposta.context['form'].errors)
        self.assertFalse(Servico.objects.filter(nome='X').exists())

    def test_editar_de_outro_negocio_retorna_404(self):
        url = reverse('painel:servico_editar', args=[self.servico_outro.pk])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(url, {'nome': 'Hack'}).status_code, 404)


class HorariosTests(PainelTestCase):
    def criar(self, dia, abertura, fechamento):
        return self.client.post(
            reverse('painel:horario_novo'),
            {'dia_semana': dia, 'abertura': abertura, 'fechamento': fechamento},
        )

    def test_criar(self):
        self.assertRedirects(self.criar(0, '09:00', '12:00'), reverse('painel:horarios'))
        horario = HorarioFuncionamento.objects.get()
        self.assertEqual(horario.negocio, self.negocio)
        self.assertEqual((horario.abertura, horario.fechamento), (time(9), time(12)))
        self.assertContains(self.client.get(reverse('painel:horarios')), 'Segunda-feira · 09:00–12:00')

    def test_faixa_sobreposta_mostra_erro(self):
        self.criar(0, '09:00', '12:00')
        resposta = self.criar(0, '11:00', '14:00')
        self.assertContains(resposta, 'sobrepõe')
        self.assertEqual(HorarioFuncionamento.objects.count(), 1)

    def test_sobreposicao_so_conta_no_proprio_negocio(self):
        HorarioFuncionamento.objects.create(
            negocio=self.outro, dia_semana=0, abertura=time(9), fechamento=time(12)
        )
        self.assertEqual(self.criar(0, '09:00', '12:00').status_code, 302)

    def test_fechamento_antes_da_abertura(self):
        resposta = self.criar(0, '18:00', '09:00')
        self.assertContains(resposta, 'depois da abertura')
        self.assertFalse(HorarioFuncionamento.objects.exists())

    def test_remover(self):
        horario = HorarioFuncionamento.objects.create(
            negocio=self.negocio, dia_semana=0, abertura=time(9), fechamento=time(12)
        )
        self.client.post(reverse('painel:horario_excluir', args=[horario.pk]))
        self.assertFalse(HorarioFuncionamento.objects.exists())

    def test_remover_de_outro_negocio_retorna_404(self):
        horario = HorarioFuncionamento.objects.create(
            negocio=self.outro, dia_semana=0, abertura=time(9), fechamento=time(12)
        )
        url = reverse('painel:horario_excluir', args=[horario.pk])
        self.assertEqual(self.client.post(url).status_code, 404)
        self.assertTrue(HorarioFuncionamento.objects.filter(pk=horario.pk).exists())


class BloqueiosTests(PainelTestCase):
    def criar(self, inicio, fim, motivo=''):
        return self.client.post(
            reverse('painel:bloqueio_novo'), {'inicio': inicio, 'fim': fim, 'motivo': motivo}
        )

    def test_criar_no_fuso_de_sao_paulo(self):
        self.assertRedirects(
            self.criar('2026-10-20T12:00', '2026-10-20T14:00', 'Dentista'),
            reverse('painel:bloqueios'),
        )
        bloqueio = Bloqueio.objects.get()
        self.assertEqual(bloqueio.negocio, self.negocio)
        self.assertEqual(bloqueio.inicio, em(date(2026, 10, 20), 12))
        self.assertEqual(bloqueio.fim, em(date(2026, 10, 20), 14))

    def test_avisa_sobre_agendamentos_no_periodo(self):
        self.agendar(em(date(2026, 10, 20), 12, 30))
        self.agendar(em(date(2026, 10, 20), 13), status=Agendamento.Status.CANCELADO)
        resposta = self.criar('2026-10-20T12:00', '2026-10-20T14:00')
        resposta = self.client.get(resposta.url)
        self.assertContains(resposta, 'Já existem 1 agendamento(s) nesse período')
        # O agendamento continua ativo: quem decide cancelar é o dono
        self.assertEqual(
            Agendamento.objects.filter(status=Agendamento.Status.AGENDADO).count(), 1
        )

    def test_fim_antes_do_inicio(self):
        resposta = self.criar('2026-10-20T14:00', '2026-10-20T12:00')
        self.assertContains(resposta, 'O fim precisa ser depois do início')
        self.assertFalse(Bloqueio.objects.exists())

    def test_lista_nao_mostra_bloqueios_passados(self):
        Bloqueio.objects.create(
            negocio=self.negocio, inicio=em(date(2026, 10, 10), 9), fim=em(date(2026, 10, 10), 18),
            motivo='Antigo',
        )
        Bloqueio.objects.create(
            negocio=self.negocio, inicio=em(date(2026, 10, 25), 9), fim=em(date(2026, 10, 25), 18),
            motivo='Futuro',
        )
        resposta = self.client.get(reverse('painel:bloqueios'))
        self.assertContains(resposta, 'Futuro')
        self.assertNotContains(resposta, 'Antigo')

    def test_remover(self):
        bloqueio = Bloqueio.objects.create(
            negocio=self.negocio, inicio=em(date(2026, 10, 20), 9), fim=em(date(2026, 10, 20), 10)
        )
        self.client.post(reverse('painel:bloqueio_excluir', args=[bloqueio.pk]))
        self.assertFalse(Bloqueio.objects.exists())

    def test_remover_de_outro_negocio_retorna_404(self):
        bloqueio = Bloqueio.objects.create(
            negocio=self.outro, inicio=em(date(2026, 10, 20), 9), fim=em(date(2026, 10, 20), 10)
        )
        url = reverse('painel:bloqueio_excluir', args=[bloqueio.pk])
        self.assertEqual(self.client.post(url).status_code, 404)
        self.assertTrue(Bloqueio.objects.filter(pk=bloqueio.pk).exists())
