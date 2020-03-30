# kappa-vedi-bot
A telegram bot for Kappa Vedi community

## Инструкция по запуску бота
1. Скачать код из репозитория github.com/avidale/kappa-vedi-bot
2. Создать MongoDB.  Доступ к продовой у @cointegrated. Тестовую можно создать самому или спросить у @akrasnow
    1. После создания тестовой MongoDB нажать Connect >> Connect your application >> Python 3.4 or later >> Скопировать ссылку. Она пригодится в пункте 7
3. Написать @BotFather и создать бота на котором будем всё тестировать. Если надо запустить продовую версию, то попросить токен у @cointegrated
4. Скачать heroku https://devcenter.heroku.com/articles/getting-started-with-python#set-up 
5. Открыть командную строку. Перейти в папку проекта и создать приложение heroku. Для этого выполнить команду в « heroku create <project_name> »
6. Отправить в heroku код проекта «git push heroku master»
7. На странице https://dashboard.heroku.com/apps выбрать созданный проект. Перейти на вкладку Settings и нажать «Reveal Config Vars». Установить переменные окружения:
    1. BASE_URL — https://<project_name>.herokuapp.com/   «<project_name>» заменить на название созданного приложения
    2. login_salt — продовый узнать у @cointegrated. Тестовый может быть любой, должен совпадать с login_salt Пиплбука
    3. MONGODB_URI — ссылка из пункта 2
    4. PBOOK_URL — url тестового пиплбука или http://kv-peoplebook.herokuapp.com
    5. TOKEN — токен из пункта 3
8. Написать /start своему боту
9. ДАЛЬШЕ ПЕРЕХОДИМ К ПИПЛБУКУ
10. Скачать код из репозитория https://github.com/avidale/peoplebook
11. Создать в heroku новое приложение для Пиплбука
12. Отправить в heroku код проекта «git push heroku master»
13. Установить переменные окружения в приложении пиплбука:
    1. APP_KEY —  для продового Пиплбука узнать у @cointegrated, для тестового подойдет что угодно, например «test_test»
    2. login_salt —  продовый узнать у @cointegrated. Тестовый может быть любой, должен совпадать с login_salt бота
    3. MONGODB_URI — ссылка из пункта 2
