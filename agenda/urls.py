from django.urls import path

from . import views

app_name = 'agenda'

urlpatterns = [
    path('<slug:slug>/', views.pagina_negocio, name='pagina_negocio'),
]
