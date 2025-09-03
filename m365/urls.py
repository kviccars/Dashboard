from django.urls import path
from . import views

urlpatterns = [
    path('lists/', views.list_sharepoint_lists, name='m365_lists'),
    path('lists/<str:list_id>/views/', views.list_views, name='m365_list_views'),
    path('timesheet/', views.timesheet_list, name='m365_timesheet'),
    path('charts/', views.charts_view, name='m365_charts'),
    path('debug-columns/', views.debug_columns, name='m365_debug_columns'),
]


