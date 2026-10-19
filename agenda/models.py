from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models
from django.db.models import F, Q

validar_whatsapp = RegexValidator(
    r'^\d{12,13}$',
    'Informe o WhatsApp só com dígitos, com DDI e DDD (ex: 5511999998888).',
)

# Prefixos de URL do próprio sistema que não podem virar link de negócio
SLUGS_RESERVADOS = {'admin', 'static', 'media', 'painel', 'conta', 'api', 'login', 'logout'}


def validar_slug_livre(valor):
    if valor.lower() in SLUGS_RESERVADOS:
        raise ValidationError('Este link é reservado pelo sistema. Escolha outro.')


class Negocio(models.Model):
    dono = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='negocios'
    )
    nome = models.CharField(max_length=100)
    slug = models.SlugField(
        unique=True, validators=[validar_slug_livre], help_text='Usado no link público: /<slug>/'
    )
    whatsapp = models.CharField(max_length=13, validators=[validar_whatsapp])
    endereco = models.CharField('endereço', max_length=200, blank=True)
    descricao = models.TextField('descrição', blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'negócio'
        ordering = ['nome']

    def __str__(self):
        return self.nome

    @property
    def link_whatsapp(self):
        return f'https://wa.me/{self.whatsapp}'


class Servico(models.Model):
    negocio = models.ForeignKey(Negocio, on_delete=models.CASCADE, related_name='servicos')
    nome = models.CharField(max_length=100)
    duracao_minutos = models.PositiveIntegerField(
        'duração (minutos)', validators=[MinValueValidator(5)]
    )
    preco = models.DecimalField('preço', max_digits=8, decimal_places=2)
    ativo = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'serviço'
        ordering = ['nome']
        constraints = [
            models.CheckConstraint(
                condition=Q(duracao_minutos__gte=5), name='servico_duracao_minima'
            ),
            models.CheckConstraint(condition=Q(preco__gte=0), name='servico_preco_nao_negativo'),
        ]

    def __str__(self):
        return self.nome

    @property
    def duracao_formatada(self):
        """Ex: 30 → '30 min', 60 → '1h', 90 → '1h30'."""
        horas, minutos = divmod(self.duracao_minutos, 60)
        if not horas:
            return f'{minutos} min'
        return f'{horas}h{minutos:02d}' if minutos else f'{horas}h'


class HorarioFuncionamento(models.Model):
    """Faixa de atendimento em um dia da semana. Pode haver mais de uma por dia (ex: almoço)."""

    class DiaSemana(models.IntegerChoices):
        # Mesma numeração de date.weekday()
        SEGUNDA = 0, 'Segunda-feira'
        TERCA = 1, 'Terça-feira'
        QUARTA = 2, 'Quarta-feira'
        QUINTA = 3, 'Quinta-feira'
        SEXTA = 4, 'Sexta-feira'
        SABADO = 5, 'Sábado'
        DOMINGO = 6, 'Domingo'

    negocio = models.ForeignKey(Negocio, on_delete=models.CASCADE, related_name='horarios')
    dia_semana = models.IntegerField('dia da semana', choices=DiaSemana.choices)
    abertura = models.TimeField()
    fechamento = models.TimeField()

    class Meta:
        verbose_name = 'horário de funcionamento'
        verbose_name_plural = 'horários de funcionamento'
        ordering = ['dia_semana', 'abertura']
        constraints = [
            models.CheckConstraint(
                condition=Q(fechamento__gt=F('abertura')),
                name='horario_fechamento_depois_abertura',
            ),
        ]

    def __str__(self):
        if self.abertura is None or self.fechamento is None:
            return f'{self.get_dia_semana_display()} (incompleto)'
        return f'{self.get_dia_semana_display()} {self.abertura:%H:%M}–{self.fechamento:%H:%M}'

    def clean(self):
        if self.abertura is None or self.fechamento is None:
            return
        if self.fechamento <= self.abertura:
            raise ValidationError('O fechamento precisa ser depois da abertura.')
        if self.negocio_id is None or self.dia_semana is None:
            return
        sobrepostos = HorarioFuncionamento.objects.filter(
            negocio_id=self.negocio_id,
            dia_semana=self.dia_semana,
            abertura__lt=self.fechamento,
            fechamento__gt=self.abertura,
        ).exclude(pk=self.pk)
        if sobrepostos.exists():
            raise ValidationError('Este horário se sobrepõe a outro do mesmo dia.')


class Bloqueio(models.Model):
    """Período em que o negócio não atende (folga, feriado, compromisso)."""

    negocio = models.ForeignKey(Negocio, on_delete=models.CASCADE, related_name='bloqueios')
    inicio = models.DateTimeField('início')
    fim = models.DateTimeField()
    motivo = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ['inicio']
        constraints = [
            models.CheckConstraint(
                condition=Q(fim__gt=F('inicio')), name='bloqueio_fim_depois_inicio'
            ),
        ]

    def __str__(self):
        if self.inicio is None or self.fim is None:
            return 'Bloqueio (incompleto)'
        return f'{self.inicio:%d/%m/%Y %H:%M} – {self.fim:%d/%m/%Y %H:%M}'

    def clean(self):
        if self.inicio and self.fim and self.fim <= self.inicio:
            raise ValidationError('O fim precisa ser depois do início.')


class Cliente(models.Model):
    negocio = models.ForeignKey(Negocio, on_delete=models.CASCADE, related_name='clientes')
    nome = models.CharField(max_length=100)
    whatsapp = models.CharField(max_length=13, validators=[validar_whatsapp])
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['nome']
        constraints = [
            models.UniqueConstraint(
                fields=['negocio', 'whatsapp'], name='cliente_whatsapp_unico_por_negocio'
            ),
        ]

    def __str__(self):
        return f'{self.nome} ({self.whatsapp})'


class Agendamento(models.Model):
    class Status(models.TextChoices):
        AGENDADO = 'agendado', 'Agendado'
        CONFIRMADO = 'confirmado', 'Confirmado'
        CANCELADO = 'cancelado', 'Cancelado'

    negocio = models.ForeignKey(Negocio, on_delete=models.CASCADE, related_name='agendamentos')
    servico = models.ForeignKey(
        Servico, on_delete=models.PROTECT, related_name='agendamentos', verbose_name='serviço'
    )
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name='agendamentos')
    inicio = models.DateTimeField('início')
    # Calculado a partir da duração do serviço em save()
    fim = models.DateTimeField(editable=False)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.AGENDADO)
    lembrete_enviado_em = models.DateTimeField(null=True, blank=True, editable=False)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['inicio']
        indexes = [models.Index(fields=['negocio', 'inicio'])]
        constraints = [
            models.CheckConstraint(
                condition=Q(fim__gt=F('inicio')), name='agendamento_fim_depois_inicio'
            ),
        ]

    def __str__(self):
        if self.cliente_id is None or self.servico_id is None or self.inicio is None:
            return 'Agendamento (incompleto)'
        return f'{self.cliente.nome} – {self.servico.nome} em {self.inicio:%d/%m/%Y %H:%M}'

    def clean(self):
        if self.servico_id and self.negocio_id and self.servico.negocio_id != self.negocio_id:
            raise ValidationError({'servico': 'Este serviço não pertence ao negócio.'})
        if self.cliente_id and self.negocio_id and self.cliente.negocio_id != self.negocio_id:
            raise ValidationError({'cliente': 'Este cliente não pertence ao negócio.'})

    def save(self, *args, **kwargs):
        self.fim = self.inicio + timedelta(minutes=self.servico.duracao_minutos)
        update_fields = kwargs.get('update_fields')
        if update_fields is not None and {'inicio', 'servico'} & set(update_fields):
            kwargs['update_fields'] = {*update_fields, 'fim'}
        super().save(*args, **kwargs)
