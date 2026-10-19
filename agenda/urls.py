from django.urls import path

from . import views

app_name = 'agenda'

urlpatterns = [
    path('<slug:slug>/', views.pagina_negocio, name='pagina_negocio'),
    path(
        '<slug:slug>/agendar/<int:servico_id>/',
        views.escolher_horario,
        name='escolher_horario',
    ),
    path(
        '<slug:slug>/agendar/<int:servico_id>/confirmar/',
        views.confirmar_agendamento,
        name='confirmar_agendamento',
    ),
    path('<slug:slug>/agendado/', views.agendamento_concluido, name='agendamento_concluido'),
]
