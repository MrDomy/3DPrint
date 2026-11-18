from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from config.exceptions import DomainError

User = get_user_model()


def user_dto(u):
    return {'id': str(u.id), 'email': u.email, 'role': u.role, 'full_name': u.full_name, 'phone': u.phone,
            'client_type': u.client_type, 'company_name': u.company_name, 'is_senior': u.is_senior}


@method_decorator(ensure_csrf_cookie, name='dispatch')
class CsrfView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        return Response({'detail': 'ok'})


@method_decorator(ensure_csrf_cookie, name='dispatch')
class MeView(APIView):
    def get(self, request):
        return Response(user_dto(request.user))


class RegisterView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        d = request.data
        email = (d.get('email') or '').strip().lower()
        password = d.get('password') or ''
        if not email or '@' not in email:
            raise DomainError('Укажите корректный email.', 'validation')
        if User.objects.filter(email=email).exists():
            raise DomainError('Пользователь с таким email уже зарегистрирован.', 'email_taken')
        if d.get('consent') not in (True, 'true', 'True', 1, '1', 'on'):
            raise DomainError('Необходимо дать согласие на обработку персональных данных.', 'consent_required')
        ctype = d.get('client_type') or 'INDIVIDUAL'
        if ctype not in ('INDIVIDUAL', 'COMPANY'):
            raise DomainError('Неверный тип клиента.', 'validation')
        if ctype == 'COMPANY' and not (d.get('company_name') or '').strip():
            raise DomainError('Укажите название организации.', 'validation')
        if not (d.get('full_name') or '').strip():
            raise DomainError('Укажите ФИО.', 'validation')
        try:
            validate_password(password)
        except ValidationError as e:
            raise DomainError(' '.join(e.messages), 'weak_password')
        u = User.objects.create_user(email=email, password=password, role='CLIENT',
                                     full_name=d['full_name'].strip(), phone=d.get('phone') or '',
                                     client_type=ctype, company_name=d.get('company_name') or '',
                                     consent_at=timezone.now())
        login(request, u, backend='django.contrib.auth.backends.ModelBackend')
        return Response(user_dto(u), status=201)


class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        email = (request.data.get('email') or '').strip().lower()
        password = request.data.get('password') or ''
        try:
            user = authenticate(request, username=email, password=password)
        except PermissionDenied:
            raise DomainError('Слишком много неудачных попыток входа. Повторите через 15 минут.', 'locked', 423)
        if user is None:
            raise DomainError('Неверный email или пароль.', 'bad_credentials', 400)
        login(request, user)
        return Response(user_dto(user))


class LogoutView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        logout(request)
        return Response({'detail': 'Вы вышли из системы.'})


class PasswordResetView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        email = (request.data.get('email') or '').strip().lower()
        u = User.objects.filter(email=email, is_active=True).first()
        if u:
            uid = urlsafe_base64_encode(force_bytes(u.pk))
            token = default_token_generator.make_token(u)
            link = f'{settings.FRONTEND_URL}/reset-password/{uid}/{token}'
            send_mail('3DPrint: восстановление пароля', f'Для смены пароля перейдите по ссылке: {link}',
                      settings.DEFAULT_FROM_EMAIL, [u.email], fail_silently=True)
        return Response({'detail': 'Если такой email зарегистрирован, мы отправили инструкцию по восстановлению.'})


class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        try:
            u = User.objects.get(pk=force_str(urlsafe_base64_decode(request.data.get('uid') or '')))
        except Exception:
            raise DomainError('Ссылка недействительна.', 'bad_token')
        if not default_token_generator.check_token(u, request.data.get('token') or ''):
            raise DomainError('Ссылка недействительна или устарела.', 'bad_token')
        pw = request.data.get('password') or ''
        try:
            validate_password(pw, u)
        except ValidationError as e:
            raise DomainError(' '.join(e.messages), 'weak_password')
        u.set_password(pw)
        u.save()
        return Response({'detail': 'Пароль изменён. Теперь вы можете войти.'})
