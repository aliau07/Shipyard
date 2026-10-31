from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from apps.projects.tests.factories import PASSWORD, make_user

from .models import User


class AuthTests(APITestCase):
    def test_login_with_username_or_email(self):
        user = make_user('nora', email='Nora@Example.com')

        by_name = self.client.post('/api/auth/token/', {'username': 'nora', 'password': PASSWORD})
        by_email = self.client.post('/api/auth/token/', {'username': 'nora@example.com', 'password': PASSWORD})

        self.assertEqual(by_name.status_code, 200)
        self.assertEqual(by_name.json()['token'], Token.objects.get(user=user).key)
        self.assertEqual(by_name.json()['user']['username'], 'nora')
        self.assertEqual(by_email.status_code, 200)

    def test_wrong_password(self):
        make_user('raj')

        response = self.client.post('/api/auth/token/', {'username': 'raj', 'password': 'nope'})

        self.assertEqual((response.status_code, response.json()['detail']), (400, 'Invalid username or password.'))

    def test_anyone_can_sign_up(self):
        response = self.client.post('/api/auth/register/', {
            'username': 'newdev', 'email': 'NEW@example.com', 'password': PASSWORD, 'first_name': 'Niamh',
        })

        self.assertEqual(response.status_code, 201)
        self.assertEqual(User.objects.get(username='newdev').email, 'new@example.com')
        self.assertIn('token', response.json())

    def test_sign_up_validation(self):
        make_user('taken', email='taken@example.com')

        response = self.client.post('/api/auth/register/', {
            'username': 'someone', 'email': 'TAKEN@example.com', 'password': '123',
        })

        self.assertEqual(response.status_code, 400)
        self.assertIn('email', response.json())

    def test_weak_passwords_are_rejected(self):
        response = self.client.post('/api/auth/register/', {
            'username': 'someone', 'email': 'someone@example.com', 'password': '12345678',
        })

        self.assertEqual(response.status_code, 400)
        self.assertIn('password', response.json())

    def test_me_and_profile_edit(self):
        user = make_user('ada')
        self.client.force_authenticate(user)

        self.assertEqual(self.client.get('/api/auth/me/').json()['display_name'], 'Ada')
        response = self.client.patch('/api/auth/me/', {'first_name': 'Ada', 'last_name': 'Byrne', 'username': 'hacker'})

        self.assertEqual(response.json()['display_name'], 'Ada Byrne')
        self.assertEqual(response.json()['username'], 'ada')

    def test_logout_revokes_the_token(self):
        user = make_user('li')
        token = Token.objects.create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')

        self.assertEqual(self.client.post('/api/auth/logout/').status_code, 204)
        self.assertFalse(Token.objects.filter(user=user).exists())
        self.assertEqual(self.client.get('/api/auth/me/').status_code, 401)
