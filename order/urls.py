from django.urls import path

from .views import *

urlpatterns = [
    path('simple', SimpleOrderView.as_view()),
    path('simple/<str:order_id>', SimpleOrderView.as_view()),
    path('pintuan/<str:action>', PinTuanOrderView.as_view()),
    path('pay/notify', pay_notify),
]
