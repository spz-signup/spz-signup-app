# -*- coding: utf-8 -*-

"""The application's administration views.

   Manages the mapping between routes and their activities for the administrators.
"""

import socket
import re
import csv
import json
from collections import namedtuple
from datetime import datetime

from redis import ConnectionError

from sqlalchemy import and_, func, not_

from flask import request, redirect, render_template, url_for, flash
from flask_login import current_user, login_required, login_user, logout_user
from flask_mail import Message

from spz import app
from spz import models, db, log
from spz.administration import TeacherManagement
from spz.decorators import templated
import spz.forms as forms
from spz.util.Filetype import mime_from_filepointer
from spz.mail import generate_status_mail

from flask_babel import gettext as _


@templated('internal/administration/teacher_overview_base.html')
def administration_teacher():
    # Aliasing might be necessary if Role or User is joined through different paths
    languages_info = db.session.query(
        models.Language.id,
        models.Language.name,
        db.func.count(models.Course.id).label('course_count'),
        db.func.count(db.distinct(models.Role.user_id)).label('teacher_count')
    ).outerjoin(
        models.Course, models.Language.id == models.Course.language_id  # Ensure all languages are included
    ).outerjoin(
        models.Role, (models.Role.course_id == models.Course.id) & (models.Role.role == models.Role.COURSE_ADMIN)
    ).group_by(
        models.Language.id, models.Language.name
    ).all()

    languages_data = [{
        'id': l_id,
        'name': name,
        'course_count': course_count if course_count else 0,
        'teacher_count': teacher_count if teacher_count else 0,
        'teacher_rate_per_course': teacher_count / course_count if course_count else 0,
    } for l_id, name, course_count, teacher_count in languages_info]

    return dict(language=languages_data)


@templated('internal/administration/teacher_overview_lang.html')
def administration_teacher_lang(id):
    lang = models.Language.query.get_or_404(id)

    teacher = models.User.query \
        .join(models.Role, models.User.roles) \
        .join(models.Course, models.Role.course_id == models.Course.id) \
        .filter(models.Course.language_id == id) \
        .distinct().all()

    return dict(language=lang, teacher=teacher)


@templated('internal/administration/add_teacher.html')
def add_teacher(id):
    lang = models.Language.query.get_or_404(id)
    form = forms.AddTeacherForm(id)

    if form.validate_on_submit():
        teacher = form.get_teacher()

        # check, if course is already assigned to a teacher
        courses = form.get_courses()
        try:
            for course in courses:
                # if course is not available, error is thrown
                TeacherManagement.check_availability(course)
        except Exception as e:
            flash(_('Der Kurs ist schon vergeben. Es kann nur eine*n Lehrbeauftragte*n je Kurs geben: %(error)s',
                    error=e), 'negative')
            return dict(language=lang, form=form)

        if teacher is None:
            roles = []
            teacher_courses = form.get_courses()
            for course in teacher_courses:
                roles.append(models.Role(course=course, role=models.Role.COURSE_ADMIN))
            teacher = models.User(email=form.get_mail(),
                                  tag=form.get_tag(),
                                  active=True,
                                  roles=roles
                                  )
            teacher.first_name = form.get_first_name()
            teacher.last_name = form.get_last_name()
            try:
                db.session.add(teacher)
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                flash(_('Es gab einen Fehler beim Hinzufügen des Lehrbeauftragten: %(error)s', error=e), 'negative')
                return dict(form=form)

        return redirect(url_for('administration_teacher_lang', id=lang.id))

    return dict(language=lang, form=form)


@templated('internal/administration/edit_teacher.html')
def edit_teacher(id):
    teacher = models.User.query.get_or_404(id)
    form = forms.EditTeacherForm()

    if form.validate_on_submit():

        try:
            teacher.first_name = form.first_name.data
            teacher.last_name = form.last_name.data
            teacher.mail = form.mail.data
            teacher.tag = form.tag.data

            db.session.commit()
            flash(_('Der/die Lehrbeauftragte wurde aktualisiert'), 'success')

            add_to_course = form.get_add_to_course()
            remove_from_course = form.get_remove_from_course()

            notify = form.get_send_mail()

            if remove_from_course:
                try:
                    success = TeacherManagement.remove_course(teacher, remove_from_course, teacher.id, notify)
                    flash(
                        _('Der/die Lehrbeauftragte wurde vom Kurs "(%(name)s)" entfernt',
                          name=remove_from_course.full_name),
                        'success')
                    db.session.commit()
                except Exception as e:
                    db.session.rollback()
                    flash(_('Der/die Lehrbeauftragte konnte nicht aus dem Kurs entfernt werden: %(error)s', error=e),
                          'negative')

            if add_to_course:
                try:
                    TeacherManagement.add_course(teacher, add_to_course, notify)
                    flash(
                        _('Der/die Lehrbeauftragte wurde zum Kurs {} hinzugefügt.'.format(add_to_course.full_name)),
                        'success'
                    )
                    db.session.commit()
                except Exception as e:
                    db.session.rollback()
                    flash(
                        _('Der/die Lehrbeauftragte konnte nicht für den Kurs eingetragen werden: %(error)s',
                          error=e),
                        'negative')

            return redirect(url_for('edit_teacher', id=teacher.id))

        except Exception as e:
            db.session.rollback()
            flash(_('Der Bewerber konnte nicht aktualisiert werden: %(error)s', error=e), 'negative')
            return dict(form=form)

    form.populate(teacher)
    return dict(teacher=teacher, form=form)


@templated('internal/teacher.html')
def teacher(id):
    teacher_db = models.User.query.get_or_404(id)

    return dict(teacher=teacher_db)


@templated('internal/administration/grade.html')
def grade(id, course_id):
    teacher_db = models.User.query.get_or_404(id)
    course = models.Course.query.get_or_404(course_id)

    exam_date = app.config['EXAM_DATE']

    return dict(teacher=teacher_db, course=course, exam_date=exam_date)


@templated('internal/administration/edit_grade.html')
def edit_grade(id, course_id):
    teacher_db = models.User.query.get_or_404(id)
    course = models.Course.query.get_or_404(course_id)
    # !!! course.course_list returns only active applicants (not on waiting list)
    GradeForm = forms.create_grade_form(course.course_list)
    form = GradeForm(request.form)

    exam_date = app.config['EXAM_DATE']

    if request.method == 'POST' and form.validate():
        try:
            for applicant in course.course_list:
                grade_field = getattr(form, f'grade_{applicant.id}')
                applicant.grade = grade_field.data

                ects_field_name = f'ects_{applicant.id}'
                if ects_field_name in request.form:
                    submitted_ects = int(request.form[ects_field_name])
                    if submitted_ects != applicant.ects_points:
                        applicant.ects_points = submitted_ects
                        flash('ECTS' + str(applicant.ects_points) + ' für ' + str(applicant.full_name), 'success')

                db.session.commit()

            flash('Noten wurden erfolgreich gespeichert!', 'success')
        except Exception as e:
            db.session.rollback()
            flash(_('Es gab einen Fehler beim Speichern der Noten: %(error)s', error=e), 'negative')

        return redirect(url_for('grade', id=id, course_id=course_id))

    return dict(teacher=teacher_db, course=course, form=form, exam_date=exam_date)


def edit_grade_view(id, course_id):
    teacher_db = models.User.query.get_or_404(id)
    course = models.Course.query.get_or_404(course_id)

    return dict(teacher=teacher_db, course=course)


@templated('internal/administration/attendances.html')
def attendances(id, course_id):
    teacher_db = models.User.query.get_or_404(id)
    course = models.Course.query.get_or_404(course_id)

    weeks = app.config['WEEKS']
    # weeks = [i for i in range(week_num)]
    return dict(teacher=teacher_db, course=course, weeks=int(weeks))


@templated('internal/administration/edit_attendances.html')
def edit_attendances(id, course_id, class_id):
    teacher_db = models.User.query.get_or_404(id)
    course = models.Course.query.get_or_404(course_id)

    return dict(teacher=teacher_db, course=course, class_id=class_id)
