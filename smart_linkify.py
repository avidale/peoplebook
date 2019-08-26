from autolink import linkify


def smart_linkify(text):
    simple_linkify = linkify(text)
    # todo: split pure text into chunks
    # todo: for each chunk (line), apply the following patterns:
    """
        
        fb: \login
        (tg|телеграм|тг|telegram):? @?\login
        @?\login - ТГ
        (vk|вк)
        tlg.wtf/\login
        instagram: \login
        
        @?\login   - по умолчанию телеграм
        
    
    непокрытое:
        Телеграм и инстаграм: @az_zakria
        Tg: Un0blogger Vk: /r.zayashnikov
        t.me/ili_masha; instagram: iliny; vk.com/mariilin
        @yeforod - instagram, telegram
        @vladmukhachev (телеграм)
        1) Телеграм @abrarovad
    """

    return simple_linkify