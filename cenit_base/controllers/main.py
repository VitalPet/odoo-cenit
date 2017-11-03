# -*- coding: utf-8 -*-

import logging
import inflect
from ast import literal_eval
import json

from odoo import http
from odoo import SUPERUSER_ID
from odoo.http import request
from odoo.modules.registry import Registry
from odoo import fields, models, api, _


_logger = logging.getLogger(__name__)


class WebhookController(http.Controller):

    @http.route(['/cenit/<string:action>',
                 '/cenit/<string:action>/<string:root>'],
                type='json', auth='none', methods=['POST'])
    def cenit_post(self, action, root=None):
        status_code = 400
        environ = request.httprequest.headers.environ.copy()
        _logger.error(environ)
        _logger.error('***************************************************')
        _logger.error(request.jsonrequest)
        params = {}
        qr = request.httprequest.query_string.split('&')
        for q in qr:
            qs = q.split('=')
            params[qs[0]] = qs[1]
        _logger.error(params)
        key = params.get('X_USER_ACCESS_KEY', False)
        token = params.get('X_USER_ACCESS_TOKEN', False)
        db_name = params.get('TENANT_DB', False)
        _logger.error("keys: %s - %s - %s", key, token, db_name)

        key = environ.get('HTTP_X_USER_ACCESS_KEY', key)
        token = environ.get('HTTP_X_USER_ACCESS_TOKEN', token)
        db_name = environ.get('HTTP_TENANT_DB', db_name)
        _logger.error("keys: %s - %s - %s", key, token, db_name)

        if not db_name:
            host = environ.get('HTTP_HOST', "")
            db_name = host.replace(".", "_").split(":")[0]

        # if db_name in http.db_list():
        registry = Registry(db_name)
        with registry.cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            connection_model = env['cenit.connection']
            domain = [('key', '=', key), ('token', '=', token)]
            _logger.info(
                "Searching for a 'cenit.connection' with key '%s' and "
                "matching token", key)
            rc = connection_model.sudo().search(domain)
            _logger.info("Candidate connections: %s", rc)
            if rc:
                p = inflect.engine()
                flow_model = env['cenit.flow']
                context = {'sender': 'client', 'action': action}
                _logger.error("inflect.engine: %s", p)
                _logger.error("root: %s", root)
                
                
                if request.jsonrequest: # root is None:
                    for root, data in request.jsonrequest.items():
                        root = p.singular_noun(root) or root
                        _logger.error("new root: %s", root)
                        data = literal_eval(data)
                        for r in data:
                            record = json.loads(r)
                            _logger.error("new record: %s", record)
                            rc = flow_model.receive(root, record)
                            if rc:
                                status_code = 200
                else:
                    root = p.singular_noun(root) or root
                    
                    _logger.error("root 1: %s", root)
                    rc = flow_model.receive( root, request.jsonrequest)
                    _logger.error("flow_model 1: %s", rc)
                    if rc:
                        status_code = 200
            else:
                status_code = 404

        return {'status': status_code}

    @http.route('/cenit/<string:root>',
        type='json', auth='none', methods=['GET'])
    def cenit_get(self, root):
        return {'status': 403}
