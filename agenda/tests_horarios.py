from datetime import date, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import TestCase

from .horarios import horario_esta_livre, horarios_livres
from .models import Agendamento, Bloqueio, Cliente, HorarioFuncionamento, Negocio, Servico

SP = ZoneInfo('America/Sao_Paulo')
SEGUNDA = date(2026, 10, 19)
# "Agora" fixo, antes do dia testado, para os testes não dependerem do relógio
ANTES = datetime(2026, 10, 18, 12, 0, tzinfo=SP)


def em(hora, minuto=0, dia=SEGUNDA):
    return datetime.combine(dia, time(hora, minuto), tzinfo=SP)


class HorariosTestCase(TestCase):
    def setUp(self):
        dono = get_user_model().objects.create_user('dono', password='senha-teste')
        self.negocio = Negocio.objects.create(
            dono=dono, nome='Barbearia', slug='barbearia', whatsapp='5511999998888'
        )
        self.corte = Servico.objects.create(
            negocio=self.negocio, nome='Corte', duracao_minutos=30, preco=Decimal('40')
        )
        self.cliente = Cliente.objects.create(
            negocio=self.negocio, nome='João', whatsapp='5511988887777'
        )

    def faixa(self, abertura, fechamento, dia=HorarioFuncionamento.DiaSemana.SEGUNDA, negocio=None):
        HorarioFuncionamento.objects.create(
            negocio=negocio or self.negocio,
            dia_semana=dia,
            abertura=abertura,
            fechamento=fechamento,
        )

    def agendar(self, inicio, servico=None, status=Agendamento.Status.AGENDADO):
        return Agendamento.objects.create(
            negocio=self.negocio,
            servico=servico or self.corte,
            cliente=self.cliente,
            inicio=inicio,
            status=status,
        )

    def livres(self, servico=None, dia=SEGUNDA, agora=ANTES, **kwargs):
        return horarios_livres(servico or self.corte, dia, agora=agora, **kwargs)


class HorariosLivresTests(HorariosTestCase):
    def test_sem_horario_de_funcionamento_nao_ha_horarios(self):
        self.assertEqual(self.livres(), [])

    def test_dia_fechado_nao_ha_horarios(self):
        self.faixa(time(9), time(12), dia=HorarioFuncionamento.DiaSemana.TERCA)
        self.assertEqual(self.livres(), [])

    def test_dia_livre_gera_horarios_a_cada_passo(self):
        self.faixa(time(9), time(11))
        self.assertEqual(self.livres(), [em(9), em(9, 30), em(10), em(10, 30)])

    def test_servico_precisa_caber_antes_do_fechamento(self):
        self.faixa(time(9), time(11))
        longo = Servico.objects.create(
            negocio=self.negocio, nome='Corte + barba', duracao_minutos=60, preco=Decimal('70')
        )
        self.assertEqual(self.livres(longo), [em(9), em(9, 30), em(10)])

    def test_servico_maior_que_a_faixa_nao_tem_horario(self):
        self.faixa(time(9), time(9, 20))
        self.assertEqual(self.livres(), [])

    def test_varias_faixas_no_dia_respeitam_intervalo_de_almoco(self):
        self.faixa(time(13), time(14))
        self.faixa(time(9), time(10))
        self.assertEqual(self.livres(), [em(9), em(9, 30), em(13), em(13, 30)])

    def test_servico_nao_atravessa_o_almoco(self):
        self.faixa(time(9), time(10))
        self.faixa(time(10, 30), time(12))
        longo = Servico.objects.create(
            negocio=self.negocio, nome='Corte + barba', duracao_minutos=60, preco=Decimal('70')
        )
        # 9:30 caberia só se o serviço pudesse continuar após o almoço
        self.assertEqual(self.livres(longo), [em(9), em(10, 30), em(11)])

    def test_agendamento_ocupa_horario(self):
        self.faixa(time(9), time(11))
        self.agendar(em(9, 30))
        self.assertEqual(self.livres(), [em(9), em(10), em(10, 30)])

    def test_agendamento_longo_bloqueia_horarios_que_colidem(self):
        self.faixa(time(9), time(11))
        longo = Servico.objects.create(
            negocio=self.negocio, nome='Corte + barba', duracao_minutos=60, preco=Decimal('70')
        )
        self.agendar(em(9, 30), servico=longo)  # 9:30–10:30
        self.assertEqual(self.livres(), [em(9), em(10, 30)])

    def test_horario_que_terminaria_dentro_de_agendamento_fica_ocupado(self):
        self.faixa(time(9), time(11))
        longo = Servico.objects.create(
            negocio=self.negocio, nome='Corte + barba', duracao_minutos=60, preco=Decimal('70')
        )
        self.agendar(em(10))  # 10:00–10:30
        # Serviço de 60 min às 9:30 iria até 10:30, colidindo
        self.assertEqual(self.livres(longo), [em(9)])

    def test_agendamento_encostado_nao_colide(self):
        self.faixa(time(9), time(10))
        self.agendar(em(9))  # termina 9:30, exatamente quando o próximo começa
        self.assertEqual(self.livres(), [em(9, 30)])

    def test_agendamento_cancelado_libera_horario(self):
        self.faixa(time(9), time(10))
        self.agendar(em(9), status=Agendamento.Status.CANCELADO)
        self.assertEqual(self.livres(), [em(9), em(9, 30)])

    def test_agendamento_confirmado_ocupa_horario(self):
        self.faixa(time(9), time(10))
        self.agendar(em(9), status=Agendamento.Status.CONFIRMADO)
        self.assertEqual(self.livres(), [em(9, 30)])

    def test_agendamento_de_outro_servico_do_mesmo_negocio_ocupa(self):
        self.faixa(time(9), time(10))
        barba = Servico.objects.create(
            negocio=self.negocio, nome='Barba', duracao_minutos=30, preco=Decimal('30')
        )
        self.agendar(em(9), servico=barba)
        self.assertEqual(self.livres(), [em(9, 30)])

    def test_agendamento_de_outro_negocio_nao_ocupa(self):
        self.faixa(time(9), time(10))
        dono = get_user_model().objects.create_user('outro', password='senha-teste')
        outro = Negocio.objects.create(
            dono=dono, nome='Outra', slug='outra', whatsapp='5511977776666'
        )
        servico_outro = Servico.objects.create(
            negocio=outro, nome='Corte', duracao_minutos=30, preco=Decimal('40')
        )
        cliente_outro = Cliente.objects.create(negocio=outro, nome='Ana', whatsapp='5511966665555')
        Agendamento.objects.create(
            negocio=outro, servico=servico_outro, cliente=cliente_outro, inicio=em(9)
        )
        self.assertEqual(self.livres(), [em(9), em(9, 30)])

    def test_bloqueio_ocupa_horarios(self):
        self.faixa(time(9), time(11))
        Bloqueio.objects.create(negocio=self.negocio, inicio=em(9, 15), fim=em(10))
        self.assertEqual(self.livres(), [em(10), em(10, 30)])

    def test_bloqueio_do_dia_inteiro(self):
        self.faixa(time(9), time(11))
        Bloqueio.objects.create(
            negocio=self.negocio,
            inicio=em(0),
            fim=datetime(2026, 10, 20, 0, 0, tzinfo=SP),
            motivo='Feriado',
        )
        self.assertEqual(self.livres(), [])

    def test_bloqueio_de_varios_dias_que_comeca_antes(self):
        self.faixa(time(9), time(11))
        Bloqueio.objects.create(
            negocio=self.negocio,
            inicio=datetime(2026, 10, 17, 0, 0, tzinfo=SP),
            fim=em(10),
            motivo='Viagem',
        )
        self.assertEqual(self.livres(), [em(10), em(10, 30)])

    def test_horarios_passados_nao_aparecem(self):
        self.faixa(time(9), time(11))
        self.assertEqual(self.livres(agora=em(9, 40)), [em(10), em(10, 30)])

    def test_horario_exatamente_agora_nao_aparece(self):
        self.faixa(time(9), time(10))
        self.assertEqual(self.livres(agora=em(9)), [em(9, 30)])

    def test_dia_que_ja_passou_nao_tem_horarios(self):
        self.faixa(time(9), time(11))
        self.assertEqual(self.livres(agora=datetime(2026, 10, 20, 8, 0, tzinfo=SP)), [])

    def test_agora_em_utc_e_comparado_corretamente(self):
        self.faixa(time(9), time(11))
        # 12:40 UTC = 9:40 em São Paulo
        agora_utc = datetime(2026, 10, 19, 12, 40, tzinfo=ZoneInfo('UTC'))
        self.assertEqual(self.livres(agora=agora_utc), [em(10), em(10, 30)])

    def test_horarios_retornados_no_fuso_de_sao_paulo(self):
        self.faixa(time(9), time(9, 30))
        [horario] = self.livres()
        self.assertEqual(horario.utcoffset(), em(9).utcoffset())
        self.assertEqual((horario.hour, horario.minute), (9, 0))

    def test_servico_inativo_nao_tem_horarios(self):
        self.faixa(time(9), time(11))
        self.corte.ativo = False
        self.corte.save()
        self.assertEqual(self.livres(), [])

    def test_passo_personalizado(self):
        self.faixa(time(9), time(10))
        self.assertEqual(
            self.livres(passo_minutos=15), [em(9), em(9, 15), em(9, 30)]
        )


class HorarioEstaLivreTests(HorariosTestCase):
    def setUp(self):
        super().setUp()
        self.faixa(time(9), time(11))

    def test_horario_livre(self):
        self.assertTrue(horario_esta_livre(self.corte, em(9, 30), agora=ANTES))

    def test_horario_ocupado(self):
        self.agendar(em(9, 30))
        self.assertFalse(horario_esta_livre(self.corte, em(9, 30), agora=ANTES))

    def test_horario_fora_do_passo(self):
        self.assertFalse(horario_esta_livre(self.corte, em(9, 10), agora=ANTES))

    def test_passo_personalizado(self):
        self.assertTrue(
            horario_esta_livre(self.corte, em(9, 15), agora=ANTES, passo_minutos=15)
        )

    def test_horario_fora_do_funcionamento(self):
        self.assertFalse(horario_esta_livre(self.corte, em(8), agora=ANTES))

    def test_aceita_inicio_em_utc(self):
        inicio_utc = datetime(2026, 10, 19, 12, 30, tzinfo=ZoneInfo('UTC'))  # 9:30 em SP
        self.assertTrue(horario_esta_livre(self.corte, inicio_utc, agora=ANTES))
