from datetime import time
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from .models import HorarioFuncionamento, Negocio, Servico


class PaginaNegocioTests(TestCase):
    def setUp(self):
        dono = get_user_model().objects.create_user('dono', password='senha-teste')
        self.negocio = Negocio.objects.create(
            dono=dono,
            nome='Barbearia do Zé',
            slug='barbearia-do-ze',
            whatsapp='5511999998888',
            endereco='Rua A, 123',
        )
        Servico.objects.create(
            negocio=self.negocio, nome='Corte', duracao_minutos=30, preco=Decimal('40.00')
        )
        Servico.objects.create(
            negocio=self.negocio, nome='Corte + barba', duracao_minutos=90, preco=Decimal('75.50')
        )
        self.url = reverse('agenda:pagina_negocio', args=['barbearia-do-ze'])

    def test_url_publica_pelo_slug(self):
        self.assertEqual(self.url, '/barbearia-do-ze/')

    def test_mostra_dados_do_negocio(self):
        resposta = self.client.get(self.url)
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'Barbearia do Zé')
        self.assertContains(resposta, 'Rua A, 123')
        self.assertContains(resposta, 'https://wa.me/5511999998888')

    def test_mostra_servicos_com_duracao_e_preco(self):
        resposta = self.client.get(self.url)
        self.assertContains(resposta, 'Corte + barba')
        self.assertContains(resposta, '30 min')
        self.assertContains(resposta, '1h30')
        self.assertContains(resposta, 'R$ 40,00')
        self.assertContains(resposta, 'R$ 75,50')

    def test_servico_inativo_nao_aparece(self):
        Servico.objects.create(
            negocio=self.negocio, nome='Luzes', duracao_minutos=60, preco=Decimal('90'), ativo=False
        )
        self.assertNotContains(self.client.get(self.url), 'Luzes')

    def test_servicos_de_outro_negocio_nao_aparecem(self):
        dono = get_user_model().objects.create_user('outro', password='senha-teste')
        outro = Negocio.objects.create(
            dono=dono, nome='Outra', slug='outra', whatsapp='5511977776666'
        )
        Servico.objects.create(negocio=outro, nome='Sobrancelha', duracao_minutos=15, preco=10)
        self.assertNotContains(self.client.get(self.url), 'Sobrancelha')

    def test_sem_servicos_mostra_aviso(self):
        self.negocio.servicos.all().delete()
        self.assertContains(self.client.get(self.url), 'Nenhum serviço disponível')

    def test_mostra_horario_de_funcionamento_agrupado_por_dia(self):
        for abertura, fechamento in [(time(13), time(18)), (time(9), time(12))]:
            HorarioFuncionamento.objects.create(
                negocio=self.negocio,
                dia_semana=HorarioFuncionamento.DiaSemana.SEGUNDA,
                abertura=abertura,
                fechamento=fechamento,
            )
        resposta = self.client.get(self.url)
        self.assertContains(resposta, 'Segunda-feira')
        self.assertContains(resposta, '09:00–12:00, 13:00–18:00')
        self.assertNotContains(resposta, 'Domingo')

    def test_slug_inexistente_retorna_404(self):
        self.assertEqual(self.client.get('/nao-existe/').status_code, 404)

    def test_admin_continua_acessivel(self):
        self.assertEqual(self.client.get('/admin/login/').status_code, 200)


class SlugReservadoTests(TestCase):
    def test_slug_reservado_invalido(self):
        dono = get_user_model().objects.create_user('dono', password='senha-teste')
        negocio = Negocio(dono=dono, nome='Admin', slug='admin', whatsapp='5511999998888')
        with self.assertRaises(ValidationError) as ctx:
            negocio.full_clean()
        self.assertIn('slug', ctx.exception.message_dict)


class DuracaoFormatadaTests(TestCase):
    def test_formatos(self):
        casos = {15: '15 min', 45: '45 min', 60: '1h', 90: '1h30', 125: '2h05'}
        for minutos, esperado in casos.items():
            with self.subTest(minutos=minutos):
                self.assertEqual(Servico(duracao_minutos=minutos).duracao_formatada, esperado)
