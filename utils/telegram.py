
from telebot import types


def render_markup(suggests=None, max_columns=3, initial_ratio=2):
    if suggests is None or len(suggests) == 0:
        return types.ReplyKeyboardRemove(selective=False)
    markup = types.ReplyKeyboardMarkup(row_width=max(1, min(max_columns, int(len(suggests) / initial_ratio))))
    markup.add(*suggests)
    return markup


def make_unique(items):
    """ an inefficient way to preserve unique elements in a list"""
    new_items = []
    for item in items:
        exists = False
        for existing in new_items:
            if existing == item:
                exists = True
                break
        if not exists:
            new_items.append(item)
    return new_items
