from flask import Blueprint, current_app, render_template
from werkzeug.datastructures import MultiDict

from flask_wtf import FlaskForm
from wtforms import StringField, BooleanField, SubmitField, TextAreaField
from wtforms.validators import DataRequired

from utils.database import Database
from peoplebook.web import SPACE_NOT_FOUND, get_current_username


admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


class LoginForm(FlaskForm):
    # key,
    title = StringField('Название сообщества', validators=[DataRequired()])
    bot_token = StringField('Токен телеграм-бота сообщества', validators=[DataRequired()])
    bot_username = StringField('Логин телеграм-бота сообщества', validators=[DataRequired()])
    peoplebook_is_public = BooleanField(
        'Пиплбук публично доступен',
        description='Если поставить эту галочку, пиплбук сможет увидеть любой пользователь'
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
    text_help_unauthorized = TextAreaField('Сообщение-help внешних пользователей')
    text_after_messages = TextAreaField('Прибаутка в собщениях бота')
    submit = SubmitField('Обновить данные')


@admin_bp.route('/<space>/details', methods=['GET', 'POST'])
def space_details(space):
    db: Database = current_app.database
    space_cfg = db.get_space(space)
    if not space_cfg:
        return SPACE_NOT_FOUND
    username = get_current_username()
    if username not in space_cfg.admins and username != space_cfg.owner_username:
        # ony admins of the space can access the settings page
        return SPACE_NOT_FOUND

    form = LoginForm()
    update_status = None
    if not form.is_submitted():
        form = LoginForm(MultiDict(space_cfg.__dict__))
    if form.validate_on_submit():
        update_dict = {
            k: v
            for k, v in form.data.items()
            if hasattr(space_cfg, k)
        }
        db.mongo_spaces.update_one({'key': space_cfg.key}, {'$set': update_dict})
        update_status = 'Изменения успешно сохранены!'

    return render_template(
        'admin_details.html',
        fields=space_cfg.__dict__,
        form=form,
        update_status=update_status,
        space=space_cfg,
    )
