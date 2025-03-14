# -*- coding: utf-8 -*-

"""Sign up management handling.

   .. note::
      Views have to be registered at the end of this module because of circular dependencies.

   .. warning::
      Some code analyzers may flag view imports as unused, because they are only imported for their side effects.
"""

import os
import random
import string

from flask import Flask
from flask_assets import Environment
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_mail import Mail
from flask_caching import Cache
from flask_wtf import CSRFProtect
from flask_babel import Babel
from flask_ckeditor import CKEditor

from jinja2 import Markup

from spz import assets
from spz.config import Development, Production, Testing


class CustomFlask(Flask):
    """Internal customizations to the Flask class.

       This is mostly for Jinja2's whitespace and newline control, and improved template performance.
    """
    jinja_options = dict(Flask.jinja_options, trim_blocks=True, lstrip_blocks=True, auto_reload=False)


app = CustomFlask(__name__, instance_relative_config=True)

# Configuration loading
if app.env == 'development':
    config_object = Development()
elif app.env == 'production':
    config_object = Production()
elif app.env == 'testing':
    config_object = Testing()
app.config.from_object(config_object)

if 'SPZ_CFG_FILE' in os.environ:
    app.config.from_pyfile(os.environ['SPZ_CFG_FILE'])  # load override values from external directory

# set up login system
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.session_protection = 'basic'


@login_manager.user_loader
def login_by_id(id):
    # local imports to avoid import before config
    from spz.models import User
    return User.query.filter(User.id == id).first()


# set up CSRF protection
CSRFProtect(app)

# helper for random length, random content comment (e.g. for BREACH protection)
rlrc_rng = random.SystemRandom()


def rlrc_comment():
    """Generate a random length (32 to 64 chars), random content (lower+upper numbers + letters) HTML comment."""
    r = rlrc_rng.randrange(32, 32 + 64)
    s = ''.join(
        rlrc_rng.choice(string.ascii_lowercase + string.ascii_uppercase + string.digits)
        for _ in range(0, r)
    )
    return Markup('<!-- RND: {} -->'.format(s))


# add Jinja helpers
app.jinja_env.globals['include_raw'] = lambda filename: Markup(app.jinja_loader.get_source(app.jinja_env, filename)[0])
app.jinja_env.globals['rlrc_comment'] = rlrc_comment
app.jinja_env.globals.update(zip=zip)

# Assets handling; keep the spz.assets module in sync with the static directory
assets_env = Environment(app)

bundles = assets.get_bundles()

for name, bundle in bundles.items():
    assets_env.register(name, bundle)

# Set up logging before anything else, in order to catch early errors
if not app.debug and app.config.get('LOGFILE', None):
    from logging import FileHandler

    file_handler = FileHandler(app.config['LOGFILE'])
    app.logger.addHandler(file_handler)

# modify app for uwsgi
if app.debug:
    from werkzeug.debug import DebuggedApplication

    app.wsgi_app = DebuggedApplication(app.wsgi_app, True)
elif app.config.get('PROFILING', False):
    from werkzeug.contrib.profiler import ProfilerMiddleware

    app.wsgi_app = ProfilerMiddleware(app.wsgi_app)
elif app.config.get('LINTING', False):
    from werkzeug.contrib.lint import LintMiddleware

    app.wsgi_app = LintMiddleware(app.wsgi_app)

# Database handling
db = SQLAlchemy(app)

# Mail sending
mail = Mail(app)

# Cache setup
cache = Cache(app, config=app.config['CACHE_CONFIG'])

# I18n setup
babel = Babel(app)

# Rich Text Editor setup
ckeditor = CKEditor(app)

# Register all views here
from spz import views, errorhandlers, pdf  # NOQA
from spz.administration import admin_views

routes = [
    ('/', views.index, ['GET', 'POST']),
    ('/signupinternal/<int:course_id>', views.signupinternal, ['GET', 'POST']),
    ('/signupexternal/<int:course_id>', views.signupexternal, ['GET', 'POST']),
    ('/licenses', views.licenses, ['GET']),
    ('/vacancies', views.vacancies, ['GET']),
    ('/signoff', views.signoff, ['GET', 'POST']),

    ('/internal/', views.internal, ['GET']),

    ('/internal/approvals/', views.approvals, ['GET']),
    ('/internal/approvals/import', views.approvals_import, ['GET', 'POST']),
    ('/internal/approvals/export', views.approvals_export, ['GET', 'POST']),
    ('/internal/approvals/check', views.approvals_check, ['GET', 'POST']),
    ('/internal/approvals/edit/<string:tag>', views.approvals_edit, ['GET', 'POST']),

    ('/internal/registrations/', views.registrations, ['GET']),
    ('/internal/registrations/import', views.registrations_import, ['GET', 'POST']),
    ('/internal/registrations/verify', views.registrations_verify, ['GET', 'POST']),

    ('/internal/print_course/<int:course_id>', pdf.print_course, ['GET']),
    ('/internal/print_course_presence/<int:course_id>', pdf.print_course_presence, ['GET']),
    ('/internal/print_language/<int:language_id>', pdf.print_language, ['GET']),
    ('/internal/print_language_presence_zip/<int:language_id>', pdf.print_language_presence_zip, ['GET']),
    ('/internal/print_language_presence/<int:language_id>', pdf.print_language_presence, ['GET']),

    ('/internal/export/<string:type>/<int:id>', views.export, ['GET', 'POST']),
    ('/internal/export/<string:type>/<int:id>/<string:format>', views.export, ['GET', 'POST']),

    ('/internal/notifications', views.notifications, ['GET', 'POST']),

    ('/internal/lists', views.lists, ['GET']),
    ('/internal/add_course', views.add_course, ['GET', 'POST']),
    ('/internal/applicant/<int:id>', views.applicant, ['GET', 'POST']),
    ('/internal/language/<int:id>', views.language, ['GET']),
    ('/internal/course/<int:id>', views.course, ['GET', 'POST']),

    ('/internal/add_attendance/<int:applicant_id>/<int:course_id>', views.add_attendance, ['GET']),
    ('/internal/remove_attendance/<int:applicant_id>/<int:course_id>', views.remove_attendance, ['GET']),

    ('/internal/applicants/search_applicant', views.search_applicant, ['GET', 'POST']),
    ('/internal/applicants/applicant_attendances/<int:id>', views.applicant_attendances, ['GET']),

    ('/internal/payments', views.payments, ['GET', 'POST']),
    ('/internal/outstanding', views.outstanding, ['GET', 'POST']),
    ('/internal/status/<int:applicant_id>/<int:course_id>', views.status, ['GET', 'POST']),
    ('/internal/print_bill/<int:applicant_id>/<int:course_id>', pdf.print_bill, ['GET']),

    ('/internal/unique', views.unique, ['GET', 'POST']),

    ('/internal/preterm', views.preterm, ['GET', 'POST']),

    ('/internal/overview_list', views.overview_export_list, ['GET', 'POST']),

    ('/internal/statistics/', views.statistics, ['GET']),
    ('/internal/statistics/free_courses', views.free_courses, ['GET']),
    ('/internal/statistics/origins_breakdown', views.origins_breakdown, ['GET']),
    ('/internal/statistics/task_queue', views.task_queue, ['GET']),

    ('/internal/duplicates', views.duplicates, ['GET']),

    ('/internal/login', views.login, ['GET', 'POST']),
    ('/internal/logout', views.logout, ['GET', 'POST']),
    ('/internal/auth/reset_password/<string:reset_token>', views.reset_password, ['GET', 'POST']),

    ('/internal/administration/teacher', admin_views.administration_teacher, ['GET', 'POST']),
    ('/internal/administration/teacher/<int:id>', admin_views.administration_teacher_lang, ['GET', 'POST']),
    ('/internal/administration/teacher/<int:id>/add', admin_views.add_teacher, ['GET', 'POST']),
    ('/internal/administration/teacher/edit/<int:id>', admin_views.edit_teacher, ['GET', 'POST']),
    ('/internal/administration/teacher/void', admin_views.teacher_void, ['GET']),
    ('/internal/teacher', admin_views.teacher, ['GET', 'POST']),
    ('/internal/grades/<int:course_id>', admin_views.grade, ['GET', 'POST']),
    ('/internal/grades/<int:course_id>/certificate_status', admin_views.markup_grade, ['GET', 'POST']),
    ('/internal/grades/<int:course_id>/edit', admin_views.edit_grade, ['GET', 'POST']),
    ('/internal/grades/<int:course_id>/edit_view', admin_views.edit_grade_view, ['GET', 'POST']),
    ('/internal/grades/<int:course_id>/import_grade', admin_views.import_grade, ['GET', 'POST']),
    ('/internal/delete_sheet/<int:file_id>', admin_views.delete_sheet, ['GET', 'POST']),
    ('/internal/download_sheet/<int:file_id>', admin_views.download_sheet, ['GET']),
    ('/internal/download_template/<int:course_id>', admin_views.download_template, ['GET']),
    ('/internal/teacher/<int:id>/attendance/<int:course_id>', admin_views.attendances, ['GET', 'POST']),
    ('/internal/teacher/<int:id>/attendance/<int:course_id>/edit/<int:class_id>', admin_views.edit_attendances,
     ['GET', 'POST']),
    ('/internal/administration/teacher/export', admin_views.teacher_export, ['GET', 'POST']),
    ('/internal/administration/teacher/import', admin_views.teacher_import, ['GET', 'POST']),

    ('/api/campus_portal/export/<string:export_token>', views.campus_portal_grades, ['GET']),
    ('/internal/campus_portal/export', views.campus_export_language, ['GET', 'POST']),
    ('/internal/campus_portal/export/<int:id>', views.campus_export_course, ['GET', 'POST']),

]

for rule, view_func, methods in routes:
    app.add_url_rule(rule, view_func=view_func, methods=methods)

handlers = [
    (400, errorhandlers.bad_request),
    (401, errorhandlers.unauthorized),
    (404, errorhandlers.page_not_found),
    (403, errorhandlers.page_forbidden),
    (410, errorhandlers.page_gone),
    (500, errorhandlers.not_found),
]

for errno, handler in handlers:
    app.register_error_handler(errno, handler)

# activate logging
from spz import log  # NOQA
