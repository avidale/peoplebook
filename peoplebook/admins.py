from flask import Blueprint, current_app, render_template, request
from werkzeug.datastructures import MultiDict

from flask_wtf import FlaskForm
from wtforms import StringField, BooleanField, SubmitField, TextAreaField, SelectField, IntegerField, HiddenField
from wtforms.validators import DataRequired

from utils.chat_data import ChatData
from utils.database import Database
from utils.spaces import MEMBERSHIP_STATUSES
from utils import wachter_utils

from peoplebook.web import SPACE_NOT_FOUND, get_current_username


admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

NONE = 'none'
YES = 'yes'
NO = 'no'
TERNARY_TUPLES = [(NONE, 'Использовать значение по умолчанию'), (YES, 'Да'), (NO, 'Нет')]


def bool_to_ternary(x):
    if x is None:
        return NONE
    return YES if x else NO


def ternary_to_bool(x):
    if x == NONE:
        return None
    elif x == YES:
        return True
    elif x == NO:
        return False
    else:
        raise ValueError(f'Value {x} cannot be converted from ternary to boolean')


class SpaceSettingsForm(FlaskForm):
    # key,
    title = StringField('Название сообщества', validators=[DataRequired()])
    bot_token = StringField('Токен телеграм-бота сообщества', validators=[DataRequired()])
    bot_username = StringField('Логин телеграм-бота сообщества', validators=[DataRequired()])
    peoplebook_is_public = BooleanField(
        'Пиплбук публично доступен',
        description='Если поставить эту галочку, пиплбук сможет увидеть любой пользователь.'
    )
    anyone_can_enter = BooleanField(
        'Открытый вход в сообщество',
        description='Если поставить эту галочку, любой пользователь Telegram, написавший боту, '
                    'получает доступ к сообществу (может заполнять пиплбук, участвовать в random coffee, и т.п.).'
    )
    member_chat_id = StringField(
        'Id чата клуба',
        description='Id основного чата клуба (где только члены) в Telegram; отрицательное число.'
    )
    guest_chat_id = StringField(
        'Id чата сообщества',
        description='Id расширенного чата клуба (где члены и гости) в Telegram; отрицательное число.'
    )
    # todo: visualize these params without making them changeable
    # owner_uid = None,
    # owner_username = 'cointegrated',
    # admins = None,
    text_help_authorized = TextAreaField('Сообщение-help для членов сообщества')
    text_help_guests = TextAreaField('Сообщение-help для гостей сообщества')
    text_help_unauthorized = TextAreaField('Сообщение-help для внешних пользователей')
    text_after_messages = TextAreaField('Прибаутка в собщениях бота')

    # wachter settings
    add_chat_members_to_community = SelectField(
        'До какого статуса поднимать участников чата',
        choices=MEMBERSHIP_STATUSES
    )
    require_whois = BooleanField('Требовать ли представления в чате')
    whois_tag = StringField(
        'Тег в представлении участника (например, #whois)',
        description='По умолчанию будет использоваться #whois'
    )
    public_chat_intro_text = TextAreaField(
        'Ответ бота на добавление участника в чат',
        description='Если не заполнить, бот сам составит сообщение'
    )
    public_chat_greeting_text = TextAreaField(
        'Ответ бота на представление участника в чате',
        description='Если не заполнить, бот сам составит сообщение'
    )
    add_whois_to_peoplebook = BooleanField('Добавлять ли представления участников в пиплбук')
    kick_timeout = IntegerField(
        'Через сколько минут удалять из чата не представившихся участников (0 - не удалять)',
    )

    feature_coffee_on = BooleanField('Включить функцию Random Coffee')
    feature_peoplebook_on = BooleanField('Включить функцию Peoplebook')

    web_show_pb_club = BooleanField('Отображать ссылку на пиплбук Клуба (привилегированных членов)')
    web_show_pb_community = BooleanField('Отображать ссылку на пиплбук Сообщества (всех членов)')
    web_show_pb_event = BooleanField('Отображать ссылку на пиплбук ближайшего события')
    web_show_pb_all = BooleanField('Отображать ссылку на пиплбук вообще всех: членов, гостей, и бывших членов')

    submit = SubmitField('Обновить данные')


class ChatsChoiceForm(FlaskForm):
    chat_id = SelectField('Выберите чат для настройки')
    submit_chat_choice = SubmitField('Выбрать чат для настройки')


class ChatSettingsForm(FlaskForm):
    chat_id = HiddenField()
    add_chat_members_to_community = SelectField(
        'До какого статуса поднимать участников чата',
        choices=MEMBERSHIP_STATUSES
    )
    require_whois = SelectField('Требовать ли представления в чате', choices=TERNARY_TUPLES)
    whois_tag = StringField('Тег в представлении участника (например, #whois)')
    public_chat_intro_text = TextAreaField('Ответ бота на добавление участника в чат')
    public_chat_greeting_text = TextAreaField('Ответ бота на представление участника в чате')
    add_whois_to_peoplebook = SelectField('Добавлять ли представления участников в пиплбук', choices=TERNARY_TUPLES)
    kick_timeout = IntegerField(
        'Через сколько минут удалять из чата не представившихся участников (0 - не удалять)',
    )
    submit_chat_settings = SubmitField('Сохранить настройки чата')


@admin_bp.route('/<space>/details', methods=['GET', 'POST'])
@admin_bp.route('/details', methods=['GET', 'POST'], subdomain='<space>')
def space_details(space):
    db: Database = current_app.database
    space_cfg = db.get_space(space)
    if not space_cfg:
        return SPACE_NOT_FOUND
    username = get_current_username()
    if username not in space_cfg.admins and username != space_cfg.owner_username:
        # ony admins of the space can access the settings page
        return SPACE_NOT_FOUND

    form = SpaceSettingsForm()
    update_status = None
    if not form.is_submitted():
        md = MultiDict(space_cfg.__dict__)
        md['kick_timeout'] = md['kick_timeout'] or 0
        form = SpaceSettingsForm(md)
    if form.validate_on_submit():
        update_dict = {
            k: v
            for k, v in form.data.items()
            if hasattr(space_cfg, k)
        }
        db.mongo_spaces.update_one({'key': space_cfg.key}, {'$set': update_dict})
        db.update_cache()
        update_status = 'Изменения успешно сохранены!'

    return render_template(
        'admin_details.html',
        fields=space_cfg.__dict__,
        form=form,
        update_status=update_status,
        space=space_cfg,
    )


@admin_bp.route('/<space>/chats', methods=['GET', 'POST'])
@admin_bp.route('/chats', methods=['GET', 'POST'], subdomain='<space>')
def chats_page(space):
    db: Database = current_app.database
    space_cfg = db.get_space(space)
    if not space_cfg:
        return SPACE_NOT_FOUND
    username = get_current_username()
    if username not in space_cfg.admins and username != space_cfg.owner_username:
        # ony admins of the space can access the settings page
        return SPACE_NOT_FOUND

    chats = db.get_chats_for_space(space_name=space_cfg.key)

    choice_form = ChatsChoiceForm()
    choice_form.chat_id.choices = [(chat.chat_id, chat.title) for chat in chats]

    chat_form = ChatSettingsForm()
    chat_form.add_chat_members_to_community.choices = MEMBERSHIP_STATUSES

    update_status = None
    the_chat: ChatData = None
    chat_id = None

    if choice_form.submit_chat_choice.data and choice_form.is_submitted():
        chat_id = int(choice_form.chat_id.data)
        update_status = f'Что-то было выбрано : {chat_id}'
    elif chat_form.submit_chat_settings.data and chat_form.is_submitted():
        chat_id = int(choice_form.chat_id.data)
        update_status = f'Был обновлён чат : {chat_id}'
    elif not chats:
        update_status = 'Ваш бот пока не добавлен ни в один чат или не имеет к ним доступа.'
    else:
        update_status = 'Выберите чат'

    if chat_id is not None:
        the_chat = db.get_chat(space_name=space_cfg.key, chat_id=chat_id)
        chat_form.chat_id.data = chat_id
    if the_chat:
        update_status = f'Настраиваем чат: {the_chat.title} ({the_chat.chat_id})'
        if chat_form.submit_chat_settings.data and chat_form.is_submitted():
            update_status = f'Пытаемся обновить чат: {the_chat.title}, но есть ошибки.'
        else:
            chat_form.add_chat_members_to_community.data = the_chat.add_chat_members_to_community
            chat_form.require_whois.data = bool_to_ternary(the_chat.require_whois)
            chat_form.whois_tag.data = the_chat.whois_tag or ''
            chat_form.public_chat_intro_text.data = the_chat.public_chat_intro_text or ''
            chat_form.public_chat_greeting_text.data = the_chat.public_chat_greeting_text or ''
            chat_form.add_whois_to_peoplebook.data = bool_to_ternary(the_chat.add_whois_to_peoplebook)
            chat_form.kick_timeout.data = the_chat.kick_timeout or 0
    else:
        chat_form = None

    if chat_form and chat_form.submit_chat_settings.data and chat_form.validate_on_submit():
        update_status = f'Обновился чат: {the_chat.title}'
        the_update = {
            'add_chat_members_to_community': chat_form.add_chat_members_to_community.data,
            'require_whois': ternary_to_bool(chat_form.require_whois.data),
            'whois_tag': chat_form.whois_tag.data or None,
            'public_chat_intro_text': chat_form.public_chat_intro_text.data or None,
            'public_chat_greeting_text': chat_form.public_chat_greeting_text.data or None,
            'add_whois_to_peoplebook': ternary_to_bool(chat_form.add_whois_to_peoplebook.data),
            'kick_timeout': int(chat_form.kick_timeout.data) or None,
        }

        db.mongo_chats.update_one(
            {'space': space, 'chat_id': chat_id},
            {'$set': the_update}
        )

    empty_chat = ChatData(chat_id=None, space=space)

    defaults = [
        ['До какого статуса поднимать участников чата', 'Не менять статус'],
        ['Требовать ли представления в чате', bool_to_ternary(space_cfg.require_whois)],
        ['Тег в представлении участника', space_cfg.whois_tag],
        ['Ответ бота на добавление участника',
         wachter_utils.get_public_chat_greeting_text(space=space_cfg, chat_data=empty_chat)],
        ['Ответ бота на представление участника',
         wachter_utils.get_public_chat_intro_text(space=space_cfg, chat_data=empty_chat)],
        ['Добавлять ли представления участников в пиплбук', bool_to_ternary(space_cfg.add_whois_to_peoplebook)],
        ['Таймаут в минутах на удаление не представившихся (0 - нет таймаута)', space_cfg.kick_timeout or 0],
    ]

    return render_template(
        'admin_chats.html',
        fields=space_cfg.__dict__,
        choice_form=choice_form,
        chat_form=chat_form,
        update_status=update_status,
        space=space_cfg,
        the_chat=the_chat,
        defaults=defaults,
    )
