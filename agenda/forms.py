import re

from django import forms

from .models import validar_whatsapp


def normalizar_whatsapp(valor):
    """'(11) 98888-7777' → '5511988887777'. Sem DDI, assume Brasil (55)."""
    digitos = re.sub(r'\D', '', valor)
    if len(digitos) in (10, 11):
        digitos = '55' + digitos
    return digitos


class AgendamentoForm(forms.Form):
    inicio = forms.DateTimeField(widget=forms.HiddenInput)
    nome = forms.CharField(max_length=100)
    whatsapp = forms.CharField(
        label='WhatsApp',
        max_length=20,
        help_text='Com DDD. Ex: (11) 98888-7777',
        widget=forms.TextInput(attrs={'inputmode': 'tel', 'autocomplete': 'tel'}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.visible_fields():
            campo.field.widget.attrs['class'] = (
                'mt-1 w-full rounded-lg border border-stone-300 px-3 py-2 '
                'focus:border-stone-900 focus:outline-none'
            )

    def clean_nome(self):
        return self.cleaned_data['nome'].strip()

    def clean_whatsapp(self):
        whatsapp = normalizar_whatsapp(self.cleaned_data['whatsapp'])
        validar_whatsapp(whatsapp)
        return whatsapp
