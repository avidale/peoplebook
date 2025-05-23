import cloudinary
import cloudinary.uploader
import os
import re
import requests
import tempfile


IMAGE_FORMATS = {"image/png", "image/jpeg", "image/jpg", "image/gif"}


def photo_url_from_message(bot, message):
    url = None
    with tempfile.TemporaryDirectory() as temp_dir:
        filename = load_photo_from_message(bot, message, directory=temp_dir)
        if filename is not None:
            url = upload_photo_to_cloudinary(filename)
    return url


def profile_photo_url_from_message(bot, message):
    url = None
    with tempfile.TemporaryDirectory() as temp_dir:
        filename = load_user_profile_photo(bot=bot, user_id=message.from_user.id, directory=temp_dir)
        if filename is not None:
            url = upload_photo_to_cloudinary(filename)
    return url


def load_photo_from_message(bot, message, directory='offline'):
    file_name = None
    file_id = None
    if message.photo is not None:
        for p in message.photo:
            file_id = p.file_id
    elif message.document is not None:
        file_id = message.document.file_id
        file_name = message.document.file_name
    if file_id is None:
        return None
    return load_photo_from_file(file_id=file_id, bot=bot, directory=directory, file_name=file_name)


def load_user_profile_photo(user_id, bot, directory='offline'):
    """ Get the local filename of the largest version of the first (leftmost) user profile photo, or None """
    photos_obj = bot.get_user_profile_photos(user_id=user_id)
    for row in photos_obj.photos:
        current_size = 0
        current_file_id = None
        for photo_obj in row:
            if photo_obj.width >= current_size:
                current_size = photo_obj.width
                current_file_id = photo_obj.file_id
        if current_size > 0:
            return load_photo_from_file(bot, current_file_id, directory=directory)


def load_photo_from_file(bot, file_id, directory='offline', file_name=None):
    file_info = bot.get_file(file_id)
    if file_name is None:
        file_name = file_info.file_path.replace('/', '__')
    downloaded_file = bot.download_file(file_info.file_path)
    full_file_name = os.path.join(directory, file_name)
    with open(full_file_name, 'wb') as f:
        f.write(downloaded_file)
    return full_file_name


def upload_photo_to_cloudinary(full_file_name):
    print('trying to upload file {} to cloudinary...'.format(full_file_name))
    cloudinary_url = os.getenv('CLOUDINARY_URL')
    if cloudinary_url is None:
        print('no url')
        return None
    matched = re.match('cloudinary://(.*):(.*)@(.*)', cloudinary_url)
    assert len(matched.groups()) == 3
    api_key, api_secret, cloud_name = matched.groups()

    uploaded = cloudinary.uploader.upload(
        full_file_name,
        api_secret=api_secret,
        api_key=api_key,
        cloud_name=cloud_name
    )
    print('file {} has been successfully uploaded to {}'.format(full_file_name, uploaded.get('url')))
    return uploaded['url']


def is_url_image(image_url):
    if not isinstance(image_url, str):
        return False
    if len(image_url) < 3:
        return False
    try:
        r = requests.head(image_url)
        if r.headers["content-type"] in IMAGE_FORMATS:
            return True
    except Exception as e:
        print(e)
    return False


def extract_photo_url_from_text(text):
    urls = re.findall('(?:http[s]?://|src="//)(?:[a-zA-Z]|[0-9]|[$_@&+.\\-~/]|[!*\\(\\),]|(?:%[0-9a-fA-F]'
                      '[0-9a-fA-F]))+', text)
    for url in urls:
        img_url = url.replace('src="//', 'http://')
        if is_url_image(img_url):
            return img_url
    return None
