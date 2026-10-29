from django.urls import path

from . import painel

app_name = 'painel'

urlpatterns = [
    path('', painel.agenda, name='agenda'),
    path('agendamentos/<int:pk>/status/', painel.alterar_status, name='alterar_status'),
    path('servicos/', painel.servicos, name='servicos'),
    path('servicos/novo/', painel.servico_form, name='servico_novo'),
    path('servicos/<int:pk>/', painel.servico_form, name='servico_editar'),
    path('horarios/', painel.horarios, name='horarios'),
    path('horarios/novo/', painel.horario_novo, name='horario_novo'),
    path('horarios/<int:pk>/excluir/', painel.horario_excluir, name='horario_excluir'),
    path('bloqueios/', painel.bloqueios, name='bloqueios'),
    path('bloqueios/novo/', painel.bloqueio_novo, name='bloqueio_novo'),
    path('bloqueios/<int:pk>/excluir/', painel.bloqueio_excluir, name='bloqueio_excluir'),
]
