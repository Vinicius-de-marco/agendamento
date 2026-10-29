import re

from django import forms

from .models import Bloqueio, HorarioFuncionamento, Servico, validar_whatsapp

CLASSE_CAMPO = (
    'mt-1 w-full rounded-lg border border-stone-300 bg-white px-3 py-2 '
    'focus:border-stone-900 focus:outline-none'
)


def normalizar_whatsapp(valor):
    """'(11) 98888-7777' → '5511988887777'. Sem DDI, assume Brasil (55)."""
    digitos = re.sub(r'\D', '', valor)
    if len(digitos) in (10, 11):
        digitos = '55' + digitos
    return digitos


class EstiloMixin:
    """Aplica as classes do Tailwind aos campos visíveis (menos caixas de seleção)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.visible_fields():
            if not isinstance(campo.field.widget, forms.CheckboxInput):
                campo.field.widget.attrs['class'] = CLASSE_CAMPO


class AgendamentoForm(EstiloMixin, forms.Form):
    inicio = forms.DateTimeField(widget=forms.HiddenInput)
    nome = forms.CharField(max_length=100)
    whatsapp = forms.CharField(
        label='WhatsApp',
        max_length=20,
        help_text='Com DDD. Ex: (11) 98888-7777',
        widget=forms.TextInput(attrs={'inputmode': 'tel', 'autocomplete': 'tel'}),
    )

    def clean_nome(self):
        return self.cleaned_data['nome'].strip()

    def clean_whatsapp(self):
        whatsapp = normalizar_whatsapp(self.cleaned_data['whatsapp'])
        validar_whatsapp(whatsapp)
        return whatsapp


# Formulários do painel: a view passa uma instância com o negócio já definido,
# para que as validações do modelo (ex: faixas sobrepostas) enxerguem o negócio.


class ServicoForm(EstiloMixin, forms.ModelForm):
    class Meta:
        model = Servico
        fields = ['nome', 'duracao_minutos', 'preco', 'ativo']
        # Aceita preço digitado como 30,00
        localized_fields = ['preco']
        widgets = {'preco': forms.TextInput(attrs={'inputmode': 'decimal'})}


class HorarioFuncionamentoForm(EstiloMixin, forms.ModelForm):
    class Meta:
        model = HorarioFuncionamento
        fields = ['dia_semana', 'abertura', 'fechamento']
        widgets = {
            'abertura': forms.TimeInput(attrs={'type': 'time'}, format='%H:%M'),
            'fechamento': forms.TimeInput(attrs={'type': 'time'}, format='%H:%M'),
        }


class BloqueioForm(EstiloMixin, forms.ModelForm):
    class Meta:
        model = Bloqueio
        fields = ['inicio', 'fim', 'motivo']
        widgets = {
            'inicio': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
            'fim': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
        }
