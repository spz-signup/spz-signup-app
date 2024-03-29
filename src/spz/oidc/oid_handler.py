# -*- coding: utf-8 -*-

"""The request handler for OpenID Connect Single Sign On with KIT institution

   Holds the data exchange funcionality.
"""

import hashlib
import json
import ssl
from urllib.parse import urlencode
from urllib.request import urlopen

import requests
import pkce

from jwkest.jwk import KEYS
from jwkest.jws import JWS

import string
import random
import base64

from spz import app

ISSUER = 'https://oidc.scc.kit.edu/auth/realms/kit'


def make_request_object(request_args, jwk):
    keys = KEYS()
    jws = JWS(request_args)

    if jwk:
        keys.load_jwks(json.dumps(dict(keys=[jwk])))

    return jws.sign_compact(keys)


def base64_urlencode(s):
    return base64.urlsafe_b64encode(s).split('='.encode('utf-8'))[0]


def get_ssl_context(config):
    """
    :return a ssl context with verify and hostnames settings
    """
    ctx = ssl.create_default_context()

    if 'verify_ssl_server' in config and not bool(config['verify_ssl_server']):
        print('Not verifying ssl certificates')
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


def decode_id_token(token: str):
    fragments = token.split(".")
    if len(fragments) != 3:
        raise Exception("Incorrect id token format: " + token)
    payload = fragments[1]
    padded = payload + '=' * (4 - len(payload) % 4)
    decoded = base64.b64decode(padded)
    return json.loads(decoded)


class Oid_handler:
    def __init__(self):
        self.credentials = {}
        self.kit_config = {}
        self.ctx = get_ssl_context(self.kit_config)
        self.meta_data_url = ISSUER + '/.well-known/openid-configuration'
        print('Fetching config from: %s' % self.meta_data_url)
        meta_data = urlopen(self.meta_data_url)
        if meta_data:
            self.kit_config.update(json.load(meta_data))
        else:
            print('Unexpected response on discovery document: %s' % meta_data)

        self.credentials['client_id'] = app.config['CLIENT_ID']
        self.credentials['secret_key'] = app.config['CLIENT_SECRET']

    def generate_state(self):
        return ''.join(random.choices(string.ascii_uppercase + string.digits, k=7))

    def generate_code_verifier(self):
        return pkce.generate_code_verifier(length=100)

    def prepare_request(self, session, scope, response_type, send_parameters_via, state,
                        code_verifier, redirect_uri):
        # state is a random string
        session['state'] = state
        # code_verifier is a string with 100 positions
        session['code_verifier'] = code_verifier
        session['flow'] = response_type
        code_challenge = pkce.get_code_challenge(code_verifier)

        request_args = {'scope': scope,
                        'response_type': response_type,
                        'client_id': self.credentials['client_id'],
                        'state': state,
                        'code_challenge': code_challenge,
                        'code_challenge_method': "S256",
                        'redirect_uri': redirect_uri}

        delimiter = "?" if self.kit_config['authorization_endpoint'].find("?") < 0 else "&"

        if send_parameters_via == "request_object":
            request_object_claims = request_args
            request_args = dict(
                request=make_request_object(request_object_claims, self.credentials.get("request_object_key", None)),
                client_id=request_args["client_id"],
                code_challenge=request_args["code_challenge"],
                code_challenge_method=request_args["code_challenge_method"],  # provided on query string
                scope=request_args["scope"],
                response_type=request_args["response_type"],
                redirect_uri=request_args["redirect_uri"]
            )
        elif send_parameters_via == "request_uri":
            request_args = None

        login_url = "%s%s%s" % (self.kit_config['authorization_endpoint'], delimiter, urlencode(request_args))

        print("Redirect to %s" % login_url)

        return login_url

    def link_extractor(self, text):
        data = {}

        snippets = text.split('?')
        response_data = snippets[1].split('&')
        for entry in response_data:
            pair = entry.split('=')
            data[pair[0]] = pair[1]

        return data

    def get_access_token(self, code, code_verifier, redirect_uri):
        """
        :param code: The code received with the authorization request
        :param code_verifier: The code challenge attribute sent in first url redirect before encoding
        :return the json response containing the tokens
        """
        token_url = self.kit_config['token_endpoint']

        data = {
            'grant_type': 'authorization_code',
            'code': code,
            'code_verifier': code_verifier,
            'redirect_uri': redirect_uri,
            'client_id': self.credentials['client_id'],
            'client_secret': self.credentials['secret_key']
        }

        # use requests lib for post request to exchange code for token
        token_response = requests.post(token_url, data=data)
        # write some log entries for easier exception handling
        print("Fetch Token request status code: {}".format(token_response.status_code))
        # write error message to logs, if request is not successful
        if not token_response.status_code == 200:
            print("Message received: {}, Request payload: {}".format(token_response.text, json.dumps(data)))
        else:
            id_token = decode_id_token(token_response.json()['id_token'])
            print("user: " + id_token['preferred_username'])
        return token_response.json()

    def request_data(self, access_token):
        """
        :param access_token: The access token received in method get_access_token to access protected resources
        """
        header = {
            'Authorization': 'Bearer {}'.format(access_token),
        }
        request_url = self.kit_config['userinfo_endpoint']
        response = requests.get(request_url, headers=header)

        # write some log entries for exception handling
        print("Access Protected resources request status code: {}".format(response.status_code))
        # write error message to logs, if request is not successful
        if not response.status_code == 200:
            for header in response.headers:
                print(header + ": " + response.headers[header])
            return response.text
        else:
            return response.json()

