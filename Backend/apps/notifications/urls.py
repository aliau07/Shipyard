from rest_framework import routers

from . import views

router = routers.SimpleRouter()
router.register('notifications', views.NotificationViewSet, basename='notification')

urlpatterns = router.urls
