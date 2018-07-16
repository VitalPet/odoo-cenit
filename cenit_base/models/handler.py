# -*- coding: utf-8 -*-

import logging
import sys

from odoo import models, api


_logger = logging.getLogger(__name__)


class CenitHandler(models.TransientModel):
    _name = 'cenit.handler'

    @api.model
    def _get_checker(self, model, field):
        def get_checker(checker):
            def _do_check(obj):
                if not obj:
                    return False
                return checker(obj)

            return _do_check

        def _dummy(obj):
            return obj

        field_type = 'other'
        try:
            field_type = getattr(model, field).to_column()._type
        except:
            pass

        return get_checker({
                               'integer': int,
                               'float': float,
                               'boolean': bool,
                               'char': str,
                               'text': str,
                               'html': str,
                               'selection': str,
                               'binary': str,
                               'date': str,
                               'datetime': str,
                           }.get(field_type, _dummy))

    @api.model
    def find(self, match, params):
        model_obj = self.env[match.model.model]

        fp = [x for x in match.lines if x.primary] or False
        if fp:
            to_search = []
            for entry in fp:
                checker = self._get_checker(model_obj, entry.name)
                _logger.error("new params: %s - %s", params, entry.value)
                value = checker(params.get(entry.value, False))
                _logger.error("new entry.value: %s - %s", entry.value, value)

                if not value:
                    continue
                to_search.append((entry.name, '=', value))

            objs = model_obj.sudo().search(to_search)
            _logger.error("new objs: %s - %s", entry.value, objs)
            if not objs and 'active' in model_obj._fields:
                to_search.append(("active", "=", False))
            objs = model_obj.sudo().search(to_search)
            _logger.error("new objs 1: %s - %s", entry.value, objs)
            if objs:
                return objs[0]

        return False

    @api.model
    def find_reference(self, match, field, params):
        f = [x for x in match.model.field_id if x.name == field.name][0]

        model_pool = self.env["ir.model"].sudo()
        model = model_pool.search([('model', '=', f.relation)])[0]
        model_obj = self.env[model.model].sudo()

        op = "="
        value = params.get(field.value, False)
        if (field.line_cardinality == "2many") and value:
            op = "in"
        to_search = [('name', op, value)]
        objs = model_obj.search(to_search)

        rc = objs or False
        if rc and (field.line_cardinality == "2one"):
            rc = rc[0].id

        return rc

    @api.model
    def process(self, match, params):
        model_obj = self.env[match.model.model]
        vals = {}

        for field in match.lines:
            if field.name == "id":
                continue
            checker = self._get_checker(model_obj, field.name)
            if field.line_type == 'field':
                if params.get(field.value, False):
                    vals[field.name] = checker(params[field.value])
            elif field.line_type == 'model':
                _logger.error("Logging: model : %s - %s ", field.name, params.get(field.value, {}))
                if field.line_cardinality == '2many':
                    vals[field.name] = []
                    for x in params.get(field.value, []):
                        item = self.process(field.reference, x)
                        _logger.error("Logging: model 1 : %s - %s  - %s", field.name, field.reference.name, item)

                        rc = self.find(field.reference, x)
                        _logger.error("Logging: model 11 : %s - %s  - %s", field.name, field.reference.name, rc)
                        tup = (0, 0, item)
                        if rc:
                            tup = (1, rc.id, item)

                        vals[field.name].append(tup)
                elif field.line_cardinality == '2one':
                    _logger.error("Logging: model 1 : %s - %s  - %s", field.name, field.reference.name, field.reference.cenit_root)
                    x = params.get(field.value, {})
                    rel_ids = self.push(x, field.reference.cenit_root)
                    _logger.error("Logging: model 2 : %s - %s ", field.name, rel_ids)
                    vals[field.name] = rel_ids and rel_ids[0] or False
            elif field.line_type == 'reference':
                vals[field.name] = self.find_reference(match, field, params)
            elif field.line_type == 'default':
                vals[field.value] = checker(field.name)

        return vals

    @api.model
    def trim(self, match, obj, vals):
        vals = vals.copy()
        obj_pool = self.env[match.model.model]

        for field in match.lines:
            if field.line_type in ("model", "reference"):
                if field.line_cardinality == "2many":
                    for record in getattr(obj, field.name):
                        if vals.get(field.name, False):
                            if record.id not in [x[1] for x in
                                                 vals[field.name]]:
                                vals[field.name].append((2, record.id, False))
                        else:
                            vals[field.name] = [(2, record.id, False)]
        return vals

    @api.model
    def get_match(self, root):
        wdt = self.env['cenit.data_type'].sudo()
        matching = wdt.search([('cenit_root', '=', root)])

        if matching:
            return matching[0]
        return False

    @api.model
    def add(self, params, m_name):
        match = self.get_match(m_name)
        if not match:
            return False

        model_obj = self.env[match.model.model]
        if not isinstance(params, list):
            params = [params]

        obj_ids = []
        for p in params:
            try:
                obj = self.find(match, p)
                if not obj:
                    _logger.error("Logging: add obj null : %s - %s", match.model.model, p)
                    vals = self.process(match, p)
                    _logger.error("Logging: add vals : %s - %s", match.model.model, vals)
                    if not vals:
                        continue
                    
                    obj = model_obj.sudo().create(vals)
                    if not obj:
                        continue
                    _logger.error("Logging: Create : %s - %s", match.model.model, obj.id)
                    self.log('Create', match.model.id,record_id=obj.id)
    
                obj_ids.append(obj.id)
            
            except Exception as e:
                _logger.error("############## Logging: Create Error : %s  ###################", match.model.model)
                _logger.exception(e)
                self.env.cr.rollback()
        return obj_ids

    @api.model
    def update(self, params, m_name):
        match = self.get_match(m_name)
        if not match:
            return False

        model_obj = self.env[match.model.model]
        if not isinstance(params, list):
            params = [params]

        obj_ids = []
        for p in params:
            try:
                obj = self.find(match, p)
                if obj:
                    vals = self.process(match, p)
                    vals = self.trim(match, obj, vals)
                    obj.sudo().write(vals)
                    obj_ids.append(obj.id)
                    _logger.error("Logging: Update : %s - %s", match.model.model, obj.id)
                    self.log('Update', match.model.id,record_id=obj.id)
            
            except Exception as e:
                _logger.error("############## Logging: Update Error : %s  ###################", match.model.model)
                _logger.exception(e)
                self.env.cr.rollback()

        return obj_ids

    @api.model
    def push(self, params, m_name):
        match = self.get_match(m_name)
        if not match:
            return False

        if not isinstance(params, list):
            params = [params]

        obj_ids = []
        commit = 0
        for p in params:
            obj = self.find(match, p)
            if obj:
                ids = self.update(p, m_name)
            else:
                ids = self.add(p, m_name)

            obj_ids.extend(ids)
            commit = commit + 1
            if commit > 10:
                self.env.cr.commit()
                commit = 0

        return obj_ids


    @api.model
    def log(self, action, model, status='Success', record_id=False, msg=''):
        if 'vitalpet_mapping' in self.env.registry._init_modules:
            res = self.env['pims.sync.log'].sudo().create({'action': action,
                                                'model': model,
                                                'status': status,
                                                'record_global_id': record_id,
                                                'msg': msg,
                                                  })
        else:
            _logger.info("Sync Logging: %s : %s - %s",action,  model, record_id)
