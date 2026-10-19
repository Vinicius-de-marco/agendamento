from datetime import datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from .models import Agendamento, Bloqueio, Cliente, HorarioFuncionamento, Negocio, Servico

SP = ZoneInfo('America/Sao_Paulo')


class ModelosTestCase(TestCase):
    def setUp(self):
        dono = get_user_model().objects.create_user('dono', password='senha-teste')
        self.negocio = Negocio.objects.create(
            dono=dono, nome='Barbearia', slug='barbearia', whatsapp='5511999998888'
        )
        self.servico = Servico.objects.create(
            negocio=self.negocio, nome='Corte', duracao_minutos=30, preco=Decimal('40.00')
        )
        self.cliente = Cliente.objects.create(
            negocio=self.negocio, nome='João', whatsapp='5511988887777'
        )

    def outro_negocio(self):
        dono = get_user_model().objects.create_user('outro', password='senha-teste')
        return Negocio.objects.create(
            dono=dono, nome='Outra', slug='outra', whatsapp='5511977776666'
        )


class AgendamentoTests(ModelosTestCase):
    def test_fim_calculado_pela_duracao_do_servico(self):
        inicio = datetime(2026, 10, 20, 9, 0, tzinfo=SP)
        ag = Agendamento.objects.create(
            negocio=self.negocio, servico=self.servico, cliente=self.cliente, inicio=inicio
        )
        self.assertEqual(ag.fim, datetime(2026, 10, 20, 9, 30, tzinfo=SP))
        self.assertEqual(ag.status, Agendamento.Status.AGENDADO)

    def test_fim_recalculado_ao_mudar_inicio(self):
        ag = Agendamento.objects.create(
            negocio=self.negocio,
            servico=self.servico,
            cliente=self.cliente,
            inicio=datetime(2026, 10, 20, 9, 0, tzinfo=SP),
        )
        ag.inicio = datetime(2026, 10, 20, 14, 0, tzinfo=SP)
        ag.save()
        self.assertEqual(ag.fim, datetime(2026, 10, 20, 14, 30, tzinfo=SP))

    def test_fim_salvo_com_update_fields(self):
        ag = Agendamento.objects.create(
            negocio=self.negocio,
            servico=self.servico,
            cliente=self.cliente,
            inicio=datetime(2026, 10, 20, 9, 0, tzinfo=SP),
        )
        ag.inicio = datetime(2026, 10, 20, 15, 0, tzinfo=SP)
        ag.save(update_fields=['inicio'])
        ag.refresh_from_db()
        self.assertEqual(ag.fim, datetime(2026, 10, 20, 15, 30, tzinfo=SP))

    def test_str_de_instancia_incompleta(self):
        self.assertEqual(str(Agendamento()), 'Agendamento (incompleto)')
        self.assertEqual(str(Bloqueio()), 'Bloqueio (incompleto)')
        self.assertIn('incompleto', str(HorarioFuncionamento(dia_semana=0)))

    def test_servico_de_outro_negocio_invalido(self):
        outro = self.outro_negocio()
        servico_outro = Servico.objects.create(
            negocio=outro, nome='Barba', duracao_minutos=20, preco=Decimal('30.00')
        )
        ag = Agendamento(
            negocio=self.negocio,
            servico=servico_outro,
            cliente=self.cliente,
            inicio=datetime(2026, 10, 20, 9, 0, tzinfo=SP),
        )
        with self.assertRaises(ValidationError) as ctx:
            ag.full_clean()
        self.assertIn('servico', ctx.exception.message_dict)

    def test_cliente_de_outro_negocio_invalido(self):
        outro = self.outro_negocio()
        cliente_outro = Cliente.objects.create(negocio=outro, nome='Ana', whatsapp='5511966665555')
        ag = Agendamento(
            negocio=self.negocio,
            servico=self.servico,
            cliente=cliente_outro,
            inicio=datetime(2026, 10, 20, 9, 0, tzinfo=SP),
        )
        with self.assertRaises(ValidationError) as ctx:
            ag.full_clean()
        self.assertIn('cliente', ctx.exception.message_dict)


class HorarioFuncionamentoTests(ModelosTestCase):
    def novo(self, abertura, fechamento, dia=HorarioFuncionamento.DiaSemana.SEGUNDA):
        return HorarioFuncionamento(
            negocio=self.negocio, dia_semana=dia, abertura=abertura, fechamento=fechamento
        )

    def test_fechamento_antes_da_abertura_invalido(self):
        with self.assertRaises(ValidationError):
            self.novo(time(18), time(9)).full_clean()

    def test_constraint_no_banco(self):
        with self.assertRaises(IntegrityError):
            self.novo(time(18), time(9)).save()

    def test_faixas_sobrepostas_no_mesmo_dia_invalidas(self):
        self.novo(time(9), time(12)).save()
        with self.assertRaises(ValidationError):
            self.novo(time(11), time(14)).full_clean()

    def test_faixas_encostadas_validas(self):
        self.novo(time(9), time(12)).save()
        self.novo(time(12), time(18)).full_clean()

    def test_mesma_faixa_em_outro_dia_valida(self):
        self.novo(time(9), time(12)).save()
        self.novo(time(9), time(12), HorarioFuncionamento.DiaSemana.TERCA).full_clean()

    def test_editar_a_propria_faixa_valido(self):
        horario = self.novo(time(9), time(12))
        horario.save()
        horario.fechamento = time(13)
        horario.full_clean()


class BloqueioTests(ModelosTestCase):
    def test_fim_antes_do_inicio_invalido(self):
        bloqueio = Bloqueio(
            negocio=self.negocio,
            inicio=datetime(2026, 10, 20, 12, 0, tzinfo=SP),
            fim=datetime(2026, 10, 20, 9, 0, tzinfo=SP),
        )
        with self.assertRaises(ValidationError):
            bloqueio.full_clean()


class ClienteTests(ModelosTestCase):
    def test_whatsapp_unico_por_negocio(self):
        with self.assertRaises(IntegrityError):
            Cliente.objects.create(negocio=self.negocio, nome='Outro', whatsapp='5511988887777')

    def test_mesmo_whatsapp_em_outro_negocio_valido(self):
        Cliente.objects.create(negocio=self.outro_negocio(), nome='João', whatsapp='5511988887777')

    def test_whatsapp_com_formatacao_invalido(self):
        cliente = Cliente(negocio=self.negocio, nome='Maria', whatsapp='(11) 98888-7777')
        with self.assertRaises(ValidationError):
            cliente.full_clean()


class ServicoTests(ModelosTestCase):
    def test_duracao_minima(self):
        servico = Servico(negocio=self.negocio, nome='Rápido', duracao_minutos=2, preco=Decimal('5'))
        with self.assertRaises(ValidationError):
            servico.full_clean()
