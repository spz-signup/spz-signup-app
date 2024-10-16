# -*- coding: utf-8 -*-
"""static functions related to administration tasks

This module contains methods for:
    - teacher management
    - course management
"""

from spz import models, db

from flask_babel import gettext as _


def get_course_ids():
    course_ids_tuple = db.session.query(models.Role.course_id).filter(
        models.Role.course_id.isnot(None)) \
        .filter(models.Role.role == models.Role.COURSE_TEACHER) \
        .distinct().all()
    # transform query tuples into right integer format
    """flash('Vergebene Kurse sind:')
    for course_id in course_ids_tuple:
        course = models.Course.query.get(course_id[0])
        flash(f'{course.full_name}: {course_id[0]}')"""
    return [course_id[0] for course_id in course_ids_tuple]


class TeacherManagement:
    @staticmethod
    def remove_course(teacher, course, user_id):
        role_to_remove = models.Role.query. \
            join(models.User.roles). \
            filter(models.Role.user_id == user_id). \
            filter(models.Role.course_id == course.id). \
            first()
        if role_to_remove:
            # remove complete table row from role table
            db.session.delete(role_to_remove)
        else:
            raise ValueError(_('Folgender Kurs "{}" war kein Kurs des/der Lehrbeauftragten.'
                               ' Wurde der richtige Kurs ausgewählt?'.format(course.full_name)))

        return course

    @staticmethod
    def add_course(teacher, course):
        own_courses_id = [course.id for course in teacher.teacher_courses]
        if course.id in own_courses_id:
            raise ValueError(
                _('Der/die Lehrbeauftragte hat diesen Kurs schon zugewiesen. Doppelzuweisung nicht möglich!'))
        TeacherManagement.check_availability(course)
        teacher.roles.append(models.Role(course=course, role=models.Role.COURSE_TEACHER))

    @staticmethod
    def check_availability(course):
        teachers = db.session.query(models.User) \
            .join(models.Role, models.User.roles) \
            .filter(models.Role.role == models.Role.COURSE_TEACHER).all()
        course_ids = get_course_ids()
        if course.id in course_ids:
            for teacher in teachers:
                if teacher.is_course_teacher(course):
                    #flash(f'{course.full_name} ({course.id}) is already assigned to {teacher.full_name}')
                    raise ValueError('{0} ist schon vergeben an {1}.'.format(course.full_name, teacher.full_name))

    @staticmethod
    def unassigned_courses(language_id):
        # courses with assigned teachers only
        unassigned_courses = db.session.query(models.Course) \
            .outerjoin(models.Role,
                       (models.Role.course_id == models.Course.id) & (models.Role.role == models.Role.COURSE_TEACHER)) \
            .join(models.Language) \
            .filter(models.Language.id == language_id) \
            .filter(models.Role.id == None)

        return unassigned_courses
