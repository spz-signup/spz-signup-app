# -*- coding: utf-8 -*-

"""All application forms.

   Manages the mapping between database models and HTML forms.
"""

import itertools

from datetime import datetime, timezone
from sqlalchemy import func, and_, or_, not_
from flask_wtf import FlaskForm, Form
from flask_login import current_user
from markupsafe import Markup

from wtforms import widgets, StringField, SelectField, SelectMultipleField, IntegerField, FloatField, Label
from wtforms import TextAreaField, BooleanField, DecimalField, MultipleFileField, HiddenField, FileField

from flask_ckeditor import CKEditorField


from wtforms.validators import DataRequired

from spz import app, models, token

from . import cached, validators

__all__ = [
    'ApplicantForm',
    'LanguageForm',
    'LoginForm',
    'PasswordResetForm',
    'NotificationForm',
    'PaymentForm',
    'PretermForm',
    'SearchForm',
    'PreSignupForm',
    'SignupFormExternal',
    'SignupFormInternal',
    'StatusForm',
    'UniqueForm',
    'TagForm',
    'SignoffForm',
    'ExportCourseForm',
    'CourseForm',
    'AddTeacherForm',
    'EditTeacherForm',
    'VacanciesForm',
    'DeleteCourseForm',
    'TriStateField',
    'TriStateLabel',
    'AttendanceForm',
    'CampusExportForm',
    'ResetLanguagePWs',
    'AddCourseForm'
]


class TriStateField(IntegerField):
    tristate_conversion = [False, None, True]

    def __init__(self, labels, **kwargs):
        super().__init__(**kwargs)
        self.labels = TriStateLabel(self.id, labels)

    def process_formdata(self, valuelist):
        try:
            self.data = TriStateField.tristate_conversion[int(valuelist[0])]
        except (TypeError, ValueError, IndexError):
            self.data = None

    @property
    def ordinal_value(self):
        try:
            return TriStateField.tristate_conversion.index(self.data)
        except ValueError:
            return 1


class TriStateLabel(Label):

    def __init__(self, field_id, text):
        super().__init__(field_id, text)
        assert len(self.text) == 3

    def __call__(self, **kwargs):
        kwargs.setdefault('for', self.field_id)
        html = ''
        for i in range(3):
            attributes = widgets.html_params(for_value=i, **kwargs)
            html += '<label %s>%s</label>' % (attributes, self.text[i])
        return Markup(html)


class SignoffForm(FlaskForm):
    signoff_id = StringField(
        'Abmelde-ID'
    )

    course = SelectField(
        'Kurse',
        coerce=int
    )

    mail = StringField(
        'Für Anmeldung verwendete E-Mailadresse'
    )

    def __init__(self, *args, **kwargs):
        super(SignoffForm, self).__init__(*args, **kwargs)
        self.course.choices = cached.all_courses_to_choicelist()

    def get_signoff_id(self):
        return self.signoff_id.data

    def get_course(self):
        return models.Course.query.get(self.course.data)

    def get_mail(self):
        return self.mail.data

    def get_applicant(self):
        existing = models.Applicant.query.filter(
            func.lower(models.Applicant.mail) == func.lower(self.get_mail())
        ).first()
        if (existing):
            return existing
        else:
            return None


class PreSignupForm(FlaskForm):
    """Represents the pre-signup form where users select if they are internal or external
    """

    type = StringField('type')
    course = SelectField(
        'Kurse',
        [validators.DataRequired('Kurs muss angegeben werden')],
        coerce=int
    )

    # Hack: The form is evaluated only once; but we want the choices to be in sync with the database values
    # see: http://wtforms.simplecodes.com/docs/0.6.1/fields.html#wtforms.fields.SelectField
    def __init__(self, show_all_courses=False, *args, **kwargs):
        super(PreSignupForm, self).__init__(*args, **kwargs)
        self._populate(show_all_courses)

    def _populate(self, show_all_courses):
        if show_all_courses:
            self.course.choices = cached.all_courses_to_choicelist()
        else:
            self.course.choices = cached.upcoming_courses_to_choicelist()

    # Accessors, to encapsulate the way the form represents and retrieves objects
    # This especially ensures that optional fields only get queried if a value is present

    def get_course(self):
        return models.Course.query.get(self.course.data)

    def get_is_internal(self):
        return self.type.data == 'internal'

    def get_is_external(self):
        return self.type.data == 'external'


class SignupFormExternal(FlaskForm):
    """Represents the main sign up form.

       Get's populated with choices from the backend.
       Gathers the user's input and validates it against the provided constraints.

       .. note:: Keep this fully cacheable (i.e. do not query the database for every new form)
    """

    first_name = StringField(
        'Vorname',
        [validators.Length(1, 60, 'Länge muss zwischen 1 und 60 Zeichen sein')]
    )
    last_name = StringField(
        'Nachname',
        [validators.Length(1, 60, 'Länge muss zwischen 1 and 60 Zeichen sein')]
    )
    # management wants to remove the phone number field
    # phone = StringField(
    #     'Telefon',
    #     [
    #         validators.Length(max=20, message='Länge darf maximal 20 Zeichen sein'),
    #         validators.PhoneValidator()
    #     ]
    # )
    mail = StringField(
        'E-Mail',
        [
            validators.Length(max=120, message='Länge muss zwischen 1 und 120 Zeichen sein'),
            validators.EmailPlusValidator()
        ]
    )

    confirm_mail = StringField(
        'E-Mail bestätigen',
        [validators.EqualTo('mail', message='E-Mailadressen müssen übereinstimmen.')]
    )

    origin = SelectField(
        'Bewerberkreis',
        [validators.DataRequired('Herkunft muss angegeben werden')],
        coerce=int
    )

    tag = StringField(
        'Sprachenzentrum ID',
        [
            validators.Length(max=30, message='Länge darf maximal 30 Zeichen sein')
        ]
    )

    course = IntegerField(
        'Kurs',
        [validators.DataRequired('Kurs muss angegeben werden')],
    )

    # Hack: The form is evaluated only once; but we want the choices to be in sync with the database values
    # see: http://wtforms.simplecodes.com/docs/0.6.1/fields.html#wtforms.fields.SelectField
    def __init__(self, course_id, *args, **kwargs):
        super(SignupFormExternal, self).__init__(*args, **kwargs)
        self._populate(course_id)

    def _populate(self, course_id):
        self.origin.choices = cached.external_origins_to_choicelist()
        self.course.data = course_id

    # Accessors, to encapsulate the way the form represents and retrieves objects
    # This especially ensures that optional fields only get queried if a value is present

    def get_first_name(self):
        return self.first_name.data

    def get_last_name(self):
        return self.last_name.data

    def get_phone(self):
        # return self.phone.data
        return None

    def get_mail(self):
        return self.mail.data

    def get_origin(self):
        return models.Origin.query.get(self.origin.data)

    def get_tag(self):
        return self.tag.data.strip() if self.tag.data and len(self.tag.data.strip()) > 0 else None  # Empty to None

    def get_course(self):
        return models.Course.query.get(self.course.data)

    # Creates an applicant or returns it from the system, if already registered.
    def get_applicant(self):
        existing = models.Applicant.query.filter(
            func.lower(models.Applicant.mail) == func.lower(self.get_mail())
        ).first()

        if existing:  # XXX: Return the applicant based on the assumption that the mail _address_ alone is an identidy
            return existing

        return models.Applicant(
            mail=self.get_mail(),
            tag=self.get_tag(),
            first_name=self.get_first_name(),
            last_name=self.get_last_name(),
            phone=self.get_phone(),
            degree=None,
            semester=None,
            origin=self.get_origin()
        )


class SignupFormInternal(FlaskForm):
    """Represents the main sign up form for internal people.

       Get's populated with choices from the backend.
       Gathers the user's input and validates it against the provided constraints.

       .. note:: Keep this fully cacheable (i.e. do not query the database for every new form)
    """

    first_name = StringField(
        'Vorname',
        [validators.Length(1, 60, 'Länge muss zwischen 1 und 60 Zeichen sein')]
    )
    last_name = StringField(
        'Nachname',
        [validators.Length(1, 60, 'Länge muss zwischen 1 and 60 Zeichen sein')]
    )
    # phone = StringField(
    #     'Telefon',
    #     [
    #         validators.Length(max=20, message='Länge darf maximal 20 Zeichen sein'),
    #         validators.PhoneValidator()
    #     ]
    # )
    mail = StringField(
        'E-Mail',
        [
            validators.Length(max=120, message='Länge muss zwischen 1 und 120 Zeichen sein'),
            validators.EmailPlusValidator()
        ]
    )

    confirm_mail = StringField(
        'E-Mail bestätigen',
        [validators.EqualTo('mail', message='E-Mailadressen müssen übereinstimmen.')]
    )

    origin = SelectField(
        'Bewerberkreis',
        [validators.DataRequired('Herkunft muss angegeben werden')],
        coerce=int
    )

    tag = StringField(
        'Matrikelnummer',
        [
            validators.Length(max=30, message='Länge darf maximal 30 Zeichen sein')
        ]
    )

    degree = SelectField(
        'Studienabschluss',
        [
            validators.RequiredDependingOnOrigin('Angabe des Studienabschlusses ist für Sie Pflicht'),
            validators.Optional()
        ],
        coerce=int
    )

    graduation = SelectField(
        'Kursabschluss (nur für statistische Zwecke)',
        [
            validators.RequiredDependingOnOrigin('Angabe des Abschlusses ist für Sie Pflicht'),
            validators.Optional()
        ],
        coerce=int
    )

    semester = IntegerField(
        'Fachsemester',
        [
            validators.RequiredDependingOnOrigin('Angabe des Fachsemesters ist für Sie Pflicht'),
            validators.Optional(),
            validators.NumberRange(min=1, max=26, message='Anzahl der Fachsemester muss zwischen 1 und 26 liegen')
        ]
    )

    state = StringField(
        'State',
        [validators.DataRequired('State muss angegeben werden')],
    )

    course = IntegerField(
        'Kurs',
        [validators.DataRequired('Kurs muss angegeben werden')],
    )

    # Hack: The form is evaluated only once; but we want the choices to be in sync with the database values
    # see: http://wtforms.simplecodes.com/docs/0.6.1/fields.html#wtforms.fields.SelectField
    def __init__(self, course_id, *args, **kwargs):
        super(SignupFormInternal, self).__init__(*args, **kwargs)
        self._populate(course_id)

    def _populate(self, course_id):
        self.degree.choices = cached.degrees_to_choicelist()
        self.graduation.choices = cached.graduations_to_choicelist()
        self.origin.choices = cached.internal_origins_to_choicelist()
        self.course.data = course_id

    # Accessors, to encapsulate the way the form represents and retrieves objects
    # This especially ensures that optional fields only get queried if a value is present

    def get_first_name(self):
        return self.first_name.data

    def get_last_name(self):
        return self.last_name.data

    def get_phone(self):
        #return self.phone.data
        return None

    def get_mail(self):
        return self.mail.data

    def get_origin(self):
        return models.Origin.query.get(self.origin.data)

    def get_degree(self):
        return models.Degree.query.get(self.degree.data) if self.degree.data else None

    def get_graduation(self):
        return models.Graduation.query.get(self.graduation.data) if self.graduation.data else None

    def get_semester(self):
        return self.semester.data if self.semester.data else None

    def get_tag(self):
        return self.tag.data if self.tag.data else None

    def get_course(self):
        return models.Course.query.get(self.course.data)

    def get_state(self):
        return self.state.data

    # Creates an applicant or returns it from the system, if already registered.
    def get_applicant(self):
        existing = models.Applicant.query.filter(
            func.lower(models.Applicant.mail) == func.lower(self.get_mail())
        ).first()

        if existing:  # XXX: Return the applicant based on the assumption that the mail _address_ alone is an identidy
            return existing

        return models.Applicant(
            mail=self.get_mail(),
            tag=self.get_tag(),
            first_name=self.get_first_name(),
            last_name=self.get_last_name(),
            phone=self.get_phone(),
            degree=self.get_degree(),
            semester=self.get_semester(),
            origin=self.get_origin()
        )


class VacanciesForm(FlaskForm):
    status_filter = SelectMultipleField(
        'Status',
        coerce=int
    )

    language_filter = SelectMultipleField(
        'Sprachen',
        coerce=int
    )

    ger_filter = SelectMultipleField(
        'GER',
        coerce=int
    )

    def __init__(self, *args, **kwargs):
        super(FlaskForm, self).__init__(*args, **kwargs)
        self._populate()

    def _populate(self):
        self.status_filter.choices = cached.course_status_to_choicelist()
        self.language_filter.choices = cached.languages_to_choicelist()
        self.ger_filter.choices = cached.gers_to_choicelist()

    def get_courses(self):
        courses = models.Course.query \
            .join(models.Language) \
            .order_by(models.Language.name) \
            .order_by(models.Course.ger) \
            .order_by(models.Course.vacancies) \
            .filter(and_(
            or_(
                not_(models.Course.is_full),
                and_(
                    models.Course.is_full,
                    models.Course.count_attendances(waiting=True) <= app.config['SHORT_WAITING_LIST'])
            )),
            and_(models.Language.signup_begin <= datetime.now(timezone.utc), models.Language.signup_end >= datetime.now(timezone.utc))
        ) \
            .all()
        return itertools.groupby(courses, lambda course: (course.language, course.ger))

    def has_courses(self):
        return True


class NotificationForm(FlaskForm):
    """Represents the form for sending notifications.

       The field's length are limited on purpose.
    """

    mail_subject = StringField(
        'Betreff',
        [validators.Length(1, 200, 'Betreff muss zwischen 1 und 200 Zeichen enthalten')]
    )
    mail_body = CKEditorField(
        'Nachricht',
        [validators.Length(1, 2000, 'Nachricht muss zwischen 1 und 2000 Zeichen enthalten')]
    )
    mail_cc = StringField(
        'CC',
        [validators.Optional()]
    )
    mail_bcc = StringField(
        'BCC',
        [validators.Optional()]
    )
    mail_courses = SelectMultipleField(
        'Kurse',
        [validators.DataRequired('Kurs muss angegeben werden')],
        coerce=int
    )
    mail_sender = SelectField(
        'Absender',
        [validators.DataRequired('Absender muss angegeben werden')],
        coerce=int
    )
    waiting_filter = TriStateField(
        default=None,
        labels=['Nur Aktive',
                'Aktive und Wartende',
                'Nur Wartende'],
        description='Die Mail kann bei Bedarf jeweils nur an aktive oder wartende Teilnehmer gesendet werden.'
    )
    unpaid_filter = TriStateField(
        default=None,
        labels=['Nur Teilnehmer ohne ausstehender Zahlung',
                'Teilnehmer mit und Teilnehmer ohne ausstehender Zahlung',
                'Nur Teilnehmer mit ausstehender Zahlung'],
        description='Die Mail kann bei Bedarf nur an Teilnehmer gesendet werden, deren Zahlung noch aussteht.'
                    ' Beide Filter können kombiniert werden.'
    )
    attachments = MultipleFileField(
        'Anhang',
        [validators.MultiFilesFileSizeValidator(0, app.config['MAIL_MAX_ATTACHMENT_SIZE'])]
    )

    def __init__(self, *args, **kwargs):
        super(NotificationForm, self).__init__(*args, **kwargs)
        # See SignupForm for this "trick"
        self.mail_courses.choices = cached.all_courses_to_choicelist()
        self.mail_sender.choices = self._sender_choices()

    def get_attachments(self):
        return self.attachments.data

    def get_courses(self):
        return models.Course.query.filter(models.Course.id.in_(self.mail_courses.data))

    def get_recipients(self):
        def flatten(x):
            return sum(x, [])

        waiting = self.waiting_filter.data
        unpaid = self.unpaid_filter.data

        recipients = set()  # One mail per recipient, even if in multiple recipient courses

        for course in self.get_courses():
            for attendance in course.filter_attendances(waiting=waiting, is_unpaid=unpaid):
                recipients.add(attendance.applicant.mail)

        return list(recipients)

    def get_body(self):
        return self.mail_body.data

    def get_subject(self):
        return self.mail_subject.data

    @staticmethod
    def _unique_mails_from_str(s):
        return list(set([mail.strip() for mail in s.split(',') if '@' in mail]))  # XXX

    def get_cc(self):
        return self._unique_mails_from_str(self.mail_cc.data)

    def get_bcc(self):
        return self._unique_mails_from_str(self.mail_bcc.data)

    def get_sender(self):
        return dict(self._sender_choices()).get(self.mail_sender.data)

    @staticmethod
    def _sender_choices():
        addresses = [current_user.email] + app.config['REPLY_TO']
        # Start index by 1 instead of 0, for the form submitting to be consistent
        return [(idx, mail) for (idx, mail) in enumerate(addresses, 1)]


class ApplicantForm(FlaskForm):  # TODO: refactor: lots of code dup. here
    """Represents the form for editing an applicant and his/her attendances.

    """
    applicant = None  # really needed?
    first_name = StringField(
        'Vorname',
        [validators.Length(1, 60, 'Länge muss zwischen 1 und 60 Zeichen sein')]
    )
    last_name = StringField(
        'Nachname',
        [validators.Length(1, 60, 'Länge muss zwischen 1 and 60 sein')]
    )
    phone = StringField(
        'Telefon',
        [validators.Length(max=20, message='Länge darf maximal 20 Zeichen sein')]
    )
    mail = StringField(
        'E-Mail',
        [
            validators.Length(max=120, message='Länge muss zwischen 1 und 120 Zeichen sein'),
            validators.EmailPlusValidator()
        ]
    )
    tag = StringField(
        'Matrikelnummer',
        [
            validators.Optional(),
            validators.Length(max=30, message='Länge darf maximal 30 Zeichen sein')
        ]
    )

    origin = SelectField(
        'Bewerberkreis',
        [validators.DataRequired('Bewerberkreis muss angegeben werden')],
        coerce=int
    )

    degree = SelectField(
        'Studienabschluss',
        [validators.Optional()],
        coerce=int
    )
    semester = IntegerField(
        'Fachsemester',
        [validators.Optional()]
    )

    add_to = SelectField(
        'Teilnahme hinzufügen',
        [validators.Optional()],
        coerce=int,
        choices=[]
    )
    remove_from = SelectField(
        'Teilnahme löschen',
        [validators.Optional()],
        coerce=int,
        choices=[]
    )
    send_mail = BooleanField(
        'Mail verschicken'
    )

    def __init__(self, *args, **kwargs):
        super(ApplicantForm, self).__init__(*args, **kwargs)
        self.origin.choices = cached.origins_to_choicelist()
        self.degree.choices = cached.degrees_to_choicelist()
        self.add_to.choices = cached.all_courses_to_choicelist()
        self.remove_from.choices = cached.all_courses_to_choicelist()

    def populate(self, applicant):
        self.applicant = applicant
        self.first_name.data = self.applicant.first_name
        self.last_name.data = self.applicant.last_name
        self.mail.data = self.applicant.mail
        self.phone.data = self.applicant.phone
        self.tag.data = self.applicant.tag
        self.origin.data = self.applicant.origin_id
        self.degree.data = self.applicant.degree.id if self.applicant.degree else None
        self.semester.data = self.applicant.semester

        in_courses_ids = [attendance.course.id for attendance in applicant.attendances]
        self.add_to.choices = [idx__ for idx__ in self.add_to.choices if idx__[0] not in in_courses_ids]
        self.remove_from.choices = [idx__1 for idx__1 in self.remove_from.choices if idx__1[0] in in_courses_ids]

    def get_applicant(self):
        return self.applicant

    def get_attendances(self):
        return self.applicant.attendances if self.applicant else None

    def get_add_to(self):
        return models.Course.query.get(self.add_to.data) if self.add_to.data else None

    def get_remove_from(self):
        return models.Course.query.get(self.remove_from.data) if self.remove_from.data else None

    def get_origin(self):
        return models.Origin.query.get(self.origin.data)

    def get_degree(self):
        return models.Degree.query.get(self.degree.data) if self.degree.data else None

    def get_semester(self):
        return self.semester.data if self.semester.data else None

    def get_send_mail(self):
        return self.send_mail.data


class StatusForm(FlaskForm):
    """Represents the form for applicants attendances and payments.

    """

    graduation = SelectField(
        'Kursabschluss',
        [validators.Optional()],
        coerce=int
    )
    registered = StringField('Registrierungsdatum')
    payingdate = StringField('Zahlungsdatum')
    waiting = BooleanField('Warteliste')
    paidbycash = BooleanField('Zahlungsart: Bar')
    discount = DecimalField(
        'Ermäßigung',
        [validators.NumberRange(min=0, max=100, message='Ungültige Prozentangabe')]
    )
    amountpaid = DecimalField(
        'Zahlbetrag',
        [validators.NumberRange(min=0, message='Keine negativen Beträge')],
        places=2
    )
    notify_change = BooleanField('Mail verschicken')

    def __init__(self, *args, **kwargs):
        super(StatusForm, self).__init__(*args, **kwargs)
        self._populate()

    def _populate(self):
        self.graduation.choices = cached.graduations_to_choicelist()

    def populate(self, attendance):
        self.graduation.data = attendance.graduation.id if attendance.graduation else None
        self.registered.data = attendance.registered
        self.payingdate.data = attendance.payingdate
        self.waiting.data = attendance.waiting
        self.discount.data = attendance.discount
        self.paidbycash.data = attendance.paidbycash
        self.amountpaid.data = attendance.amountpaid

    def get_graduation(self):
        return models.Graduation.query.get(self.graduation.data) if self.graduation.data else None


class PaymentForm(FlaskForm):
    """Represents a PaymentForm to input the attendance

    """

    confirmation_code = StringField(
        'Code',
        [validators.Length(min=4, message='Länge muss mindestens 4 Zeichen lang sein')]
    )


class SearchForm(FlaskForm):
    """Represents a form to search for specific applicants.
    """

    query = StringField(
        'Suchen',
        [validators.DataRequired('Suchparameter muss angegeben werden')]
    )


class LanguageForm(FlaskForm):
    """Represents a form for working with courses based on the user's language selection.
    """

    language = SelectField(
        'Sprache',
        [validators.DataRequired('Die Sprache muss angegeben werden')],
        coerce=int
    )

    def __init__(self, *args, **kwargs):
        super(LanguageForm, self).__init__(*args, **kwargs)
        self._populate()

    def _populate(self):
        self.language.choices = cached.languages_to_choicelist()

    def get_courses(self):
        return models.Language.query.get(self.language.data).courses


class UniqueForm(LanguageForm):
    """Represents a form to fill languages and courses with waiting applicants.
    """
    pass


class DeleteCourseForm(FlaskForm):
    """Represents a form for deleting a course.
    """
    identifier = StringField()


class PretermForm(FlaskForm):
    """Represents a form to generate a preterm signup token.
    """

    mail = StringField(
        'E-Mail',
        [
            validators.Length(max=120, message='Länge muss zwischen 1 und 120 Zeichen sein'),
            validators.EmailPlusValidator()
        ]
    )

    def get_token(self):
        return token.generate(self.mail.data, namespace='preterm')


class LoginForm(FlaskForm):
    """Represents the login form the the internal partsPasswort
    """

    user = StringField('Email', [validators.DataRequired('User muss angegeben werden')])
    password = StringField('Passwort', [validators.DataRequired('Passwort muss angegeben werden')])


class PasswordResetForm(FlaskForm):
    """Represents the password reset form
    """
    pw_length = 8
    reset_token = StringField('Reset Token', [validators.DataRequired('Reset Token muss angegeben werden')])
    password = StringField('Passwort', [validators.DataRequired('Passwort muss angegeben werden'),
                                        validators.Length(min=pw_length,
                                                          message='Das Passwort muss mindestens %(min)d Zeichen haben.')])
    confirm_pw = StringField(
        'Passwort Bestätigen',
        [validators.EqualTo('password', message='Passwörter müssen übereinstimmen.')]
    )

    def __init__(self, *args, **kwargs):
        super(PasswordResetForm, self).__init__(*args, **kwargs)

    def get_pw_length(self):
        return self.pw_length

class TagForm(FlaskForm):
    """Represents the form for the input of a tag.
    """

    tag = StringField(
        'Matrikelnummer oder Kürzel'
    )

    def get_tag(self):
        return self.tag.data


class ExportCourseForm(FlaskForm):
    """Form for exporting one or multiple courses.

       Export format choices differ, depending on the passed language list (current_user.languages).
       It might be an option to use the value of 'courses' instead.
    """

    courses = SelectMultipleField(
        'Kurse',
        [validators.DataRequired('Mindestens ein Kurs muss ausgewählt werden')],
        coerce=int
    )

    format = SelectField(
        'Format',
        [validators.DataRequired('Das Format muss angegeben werden')],
        coerce=int
    )

    def get_format(self):
        return models.ExportFormat.query.get(self.format.data)

    def get_selected(self):
        return [models.Course.query.get(id) for id in self.courses.data]

    def __init__(self, languages=[], *args, **kwargs):
        super(ExportCourseForm, self).__init__(*args, **kwargs)
        self.courses.choices = cached.all_courses_to_choicelist()
        # get choices on course wise level
        self.format.choices = [
            (f.id, f.descriptive_name) for f in models.ExportFormat.list_formatters(languages=languages)
        ]

    def update_course_list(self, user):
        # fetch courses depending on user
        if user.is_admin_or_superuser:
            new_choices = cached.all_courses_to_choicelist()
            if self.courses.choices != new_choices:
                self.courses.choices = new_choices
        else:
            courses = getattr(user, 'teacher_courses', [])
            new_choices = [(course.id, course.full_name) for course in courses]
            if self.courses.choices != new_choices:
                self.courses.choices = new_choices


class ExportOverviewForm(FlaskForm):
    """Form for exporting the semester list overview of all courses of a language.

    """

    language = SelectField(
        'Sprache',
        [validators.DataRequired('Die Sprache muss ausgewählt werden')],
        coerce=int
    )

    format = SelectField(
        'Format',
        [validators.DataRequired('Das Export-Format muss angegeben werden')],
        coerce=int
    )

    only_passed = BooleanField(
        'Nur Studierende mit \'bestanden\' exportieren'
    )

    def get_selected(self):
        return models.Language.query.get(self.language.data)

    def get_format(self):
        return models.ExportFormat.query.get(self.format.data)

    def get_passed(self):
        return self.only_passed.data

    def __init__(self, languages=[], *args, **kwargs):
        super(ExportOverviewForm, self).__init__(*args, **kwargs)
        self.language.choices = cached.languages_to_choicelist()
        # get choices on language wise level
        self.format.choices = [
            (f.id, f.descriptive_name) for f in
            models.ExportFormat.list_formatters(languages=languages, instance=models.ExportFormat.LANGUAGE)
        ]


class AddTeacherForm(FlaskForm):
    """Represents the form to add teachers to database.

    """
    first_name = StringField(
        'Vorname',
        [validators.Length(1, 60, 'Länge muss zwischen 1 und 60 Zeichen sein')]
    )
    last_name = StringField(
        'Nachname',
        [validators.Length(1, 60, 'Länge muss zwischen 1 and 60 Zeichen sein')]
    )

    mail = StringField(
        'E-Mail',
        [
            validators.Length(max=120, message='Länge muss zwischen 1 und 120 Zeichen sein'),
            validators.EmailPlusValidator()
        ]
    )

    confirm_mail = StringField(
        'E-Mail bestätigen',
        [validators.EqualTo('mail', message='E-Mailadressen müssen übereinstimmen.')]
    )

    tag = StringField(
        'Mitarbeiterkürzel',
        [
            validators.Length(max=10, message='Länge darf maximal 10 Zeichen sein')
        ]
    )

    courses = SelectMultipleField(
        'Kurse',
        [validators.DataRequired('Mindestens ein Kurs muss ausgewählt werden')],
        coerce=int
    )

    send_mail = BooleanField(
        'Passwort-Mail verschicken'
    )

    def __init__(self, language_id, *args, **kwargs):
        super(AddTeacherForm, self).__init__(*args, **kwargs)
        self.courses.choices = cached.language_to_choicelist(language_id, True)

    def update_courses(self, language_id):
        self.courses.choices = cached.language_to_choicelist(language_id, True)

    def get_first_name(self):
        return self.first_name.data

    def get_last_name(self):
        return self.last_name.data

    def get_mail(self):
        return self.mail.data

    def get_tag(self):
        return self.tag.data

    def get_send_mail(self):
        return self.send_mail.data

    def get_courses(self):
        return [models.Course.query.get(id) for id in self.courses.data]

    def get_teacher(self):
        existing = models.User.query.filter(
            func.lower(models.User.email) == func.lower(self.get_mail())
        ).first()
        if existing:
            return existing
        else:
            return None


class EditTeacherForm(FlaskForm):
    """Represents the form for editing a teacher and his/her courses and languages.

    """
    first_name = StringField(
        'Vorname',
        [validators.Length(1, 60, 'Länge muss zwischen 1 und 60 Zeichen sein')]
    )
    last_name = StringField(
        'Nachname',
        [validators.Length(1, 60, 'Länge muss zwischen 1 and 60 sein')]
    )
    mail = StringField(
        'E-Mail',
        [
            validators.Length(max=120, message='Länge muss zwischen 1 und 120 Zeichen sein'),
            validators.EmailPlusValidator()
        ]
    )
    tag = StringField(
        'Mitarbeiterkürzel',
        [
            validators.Optional(),
            validators.Length(max=30, message='Länge darf maximal 30 Zeichen sein')
        ]
    )

    add_to_course = SelectMultipleField(
        'Kurs hinzufügen',
        [validators.Optional()],
        coerce=int,
        choices=[]
    )
    remove_from_course = SelectField(
        'Kurs löschen',
        [validators.Optional()],
        coerce=int,
        choices=[]
    )

    send_mail = BooleanField(
        'Passwort zurücksetzen und Mail verschicken'
    )

    def __init__(self, teacher, *args, **kwargs):
        super(EditTeacherForm, self).__init__(*args, **kwargs)
        self.teacher = teacher

        self.add_to_course.choices = cached.all_courses_to_choicelist()
        self.remove_from_course.choices = cached.own_courses_to_choicelist(teacher)

    def populate(self):
        self.first_name.data = self.teacher.first_name
        self.last_name.data = self.teacher.last_name
        self.mail.data = self.teacher.email
        self.tag.data = self.teacher.tag
        # reload choices (if course is added needs to be updated)
        self.remove_from_course.choices = cached.own_courses_to_choicelist(self.teacher)

    def get_teacher(self):
        return self.teacher

    def get_courses(self):
        sorted_courses = sorted(self.teacher.teacher_courses, key=lambda x: x.full_name)
        return sorted_courses

    def get_languages(self):
        language_ids = []
        languages = []
        if self.teacher is not None:
            for course in self.teacher.teacher_courses:
                if course.language_id not in language_ids:
                    language_ids.append(course.language_id)
                    db_lang = models.Language.query.get_or_404(course.language_id)
                    languages.append(db_lang)

        return languages if languages else None

    def get_add_to_course(self):
        return [models.Course.query.get(course_id) for course_id in self.add_to_course.data] if self.add_to_course.data else None

    def get_remove_from_course(self):
        return models.Course.query.get(self.remove_from_course.data) if self.remove_from_course.data else None

    def get_send_mail(self):
        return self.send_mail.data


class CourseForm(FlaskForm):
    """ A form to select different participants in that specific course
    """
    identifier = StringField()


def create_grade_form(applicants, course_id):
    """
    Dynamically creates a GradeForm class with fields for each applicant.
    """

    class GradeForm(FlaskForm):
        pass

    for applicant in applicants:
        attendance = models.Attendance.query.filter_by(applicant_id=applicant.id, course_id=course_id).first()
        field_name = f'grade_{applicant.id}'
        setattr(GradeForm, field_name,
                FloatField("Note", validators=[validators.Optional(), validators.NumberRange(min=0, max=100)],
                             default=attendance.grade))

    return GradeForm


class AttendanceForm(FlaskForm):
    attendance = HiddenField("attendance_id")


class CampusExportForm(FlaskForm):
    """
    Represents the form for exporting the grades of the applicants to the Campus System.
    """

    courses = SelectField(
        'Kurse',
        coerce=str
    )

    def __init__(self, grouped_by_level, *args, **kwargs):
        super(CampusExportForm, self).__init__(*args, **kwargs)
        self.courses.choices = cached.grouped_by_level_to_choicelist(grouped_by_level)

    def get_courses(self):
        return self.courses.data

    def update_course(self, grouped_by_level):
        self.courses.choices = cached.grouped_by_level_to_choicelist(grouped_by_level)


class ResetLanguagePWs(FlaskForm):
    """Represents the form for send pws to all teachers of a language."""

    def __init__(self, language, *args, **kwargs):
        super(ResetLanguagePWs, self).__init__(*args, **kwargs)
        self.language = language
        self.send_mail.label.text = f'Passwort für alle Dozenten von {language.name} zurücksetzen'

    send_mail = BooleanField()

    def get_send_mail(self):
        return self.send_mail.data


def create_approval_form(tag):
    class EditApprovalForm(FlaskForm):
        pass

    approvals = models.Approval.get_for_tag(tag)
    for approval in approvals:
        field_name = f'approval_{approval.id}'
        setattr(EditApprovalForm, field_name,
                IntegerField("Test", validators=[validators.DataRequired(), validators.NumberRange(min=0, max=100)],
                             default=approval.percent))

        priority_field_name = f'priority_{approval.id}'
        setattr(EditApprovalForm, priority_field_name,
                BooleanField("Priorität", default=approval.priority))

    return EditApprovalForm

def excel_file_validator(form, field):
    # Check if the uploaded file has a .xlsx or .xls extension
    if field.data:
        filename = field.data.filename
        if not (filename.endswith('.xlsx')):
            raise validators.ValidationError("Die hochgeladene Datei muss eine Excel-Datei sein (Format: *.xlsx).")

class ImportGradeForm(FlaskForm):
    file = FileField('Datei', validators=[validators.DataRequired(), excel_file_validator])


class AddCourseForm(FlaskForm):
    language = SelectField(
        'Sprache',
        coerce=int
    )
    level = StringField(
        'Kursname',
        validators=[validators.Length(min=1, max=120, message="Der Kursname darf nicht leer sein. (max. 120 Zeichen)")]
    )
    alternative = SelectField(
        'Kurszusatz',
        coerce=int,
        default=0
    ) # put "", a to z
    limit = IntegerField(
        'Teilnehmerzahl', validators=[validators.Optional(), validators.NumberRange(min=0, max=40)]
    )
    price = IntegerField(
        'Preis', validators=[validators.Optional(), validators.NumberRange(min=0, max=500)]
    )
    ger = SelectField(
        'GER-Level',
        coerce=str
    )  # A1, A2, B1, B2, C1, C2
    rating_highest = IntegerField(
        'Höchste Bewertung', validators=[validators.Optional(), validators.NumberRange(min=0, max=100)]
    )
    rating_lowest = IntegerField(
        'Niedrigste Bewertung', validators=[validators.Optional(), validators.NumberRange(min=0, max=100)]
    )
    # has waiting list = True
    ects = SelectField(
        'ECTS Leistungspunkte',
        coerce=int,
        default=2
    ) # 2, 3, 4

    def __init__(self, *args, **kwargs):
        super(AddCourseForm, self).__init__(*args, **kwargs)
        self._populate()

    def _populate(self):
        self.language.choices = cached.languages_to_choicelist()
        self.alternative.choices = [(0, ' ')] + [(97 + i, "{0}".format(chr(97 + i))) for i in range(26)]
        self.ger.choices = cached.gers_to_choicelist()
        self.ects.choices = [(i, "{0}".format(str(i))) for i in range(2, 5)]

    def get_alternative(self):
        if self.alternative.data != 0:
            return chr(self.alternative.data)  # Convert ASCII integer to a lowercase letter
        return ""

    def get_ger(self):
        if self.ger.data == "None":
            return None
        return self.ger.data

    def get_limit(self):
        if self.limit.data is None:
            return 25
        return self.limit.data

    def get_price(self):
        if self.price.data is None:
            return 90
        return self.price.data

    def get_rating_lowest(self):
        if self.rating_lowest.data is None:
            return 0
        return self.rating_lowest.data

    def get_rating_highest(self):
        if self.rating_highest.data is None:
            return 100
        return self.rating_highest.data
