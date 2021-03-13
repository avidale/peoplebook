class InvitationStatuses:
    NOT_SENT = 'NOT_SENT'
    NOT_ANSWERED = 'NOT_ANSWERED'
    ON_HOLD = 'ON_HOLD'
    ACCEPT = 'ACCEPT'
    REJECT = 'REJECT'
    NOT_ANSWERED_OVERDUE = 'NOT_ANSWERED_OVERDUE'
    ON_HOLD_OVERDUE = 'ON_HOLD_OVERDUE'
    NOT_SENT_OVERDUE = 'NOT_SENT_OVERDUE'

    PAYMENT_PAID = 'PAID'
    PAYMENT_NOT_PAID = 'NOT_PAID'

    @classmethod
    def translate(cls, status, payment_status=None):
        d = {
            cls.NOT_SENT: 'не получено',
            cls.NOT_ANSWERED: 'без ответа',
            cls.ON_HOLD: 'думает',
            cls.ACCEPT: 'да',
            cls.REJECT: 'нет',
            cls.ON_HOLD_OVERDUE: 'так и не решил(а)',
            cls.NOT_SENT_OVERDUE: 'так и не получено',
            cls.NOT_ANSWERED_OVERDUE: 'так и нет ответа'
        }
        result = d.get(status, 'какой-то непонятный статус')
        if status == cls.ACCEPT and payment_status != cls.PAYMENT_PAID:
            result = result + ' (не оплачено)'
        return result

    @classmethod
    def translate_second_person(cls, status):
        d = {
            cls.NOT_SENT: 'Вы не участвуете',
            cls.NOT_ANSWERED: 'Вы пока не решили, участвовать ли',
            cls.ON_HOLD: 'Вы пока не решили, участвовать ли',
            cls.ACCEPT: 'Вы участвуете',
            cls.REJECT: 'Вы не участвуете',
            cls.ON_HOLD_OVERDUE: 'Вы не участвовали',
            cls.NOT_SENT_OVERDUE: 'Вы не участвовали',
            cls.NOT_ANSWERED_OVERDUE: 'Вы не участвовали'
        }
        return d.get(status, 'какой-то непонятный статус')

    @classmethod
    def undecided_states(cls):
        return [cls.NOT_SENT, cls.NOT_ANSWERED, cls.ON_HOLD]

    @classmethod
    def success_states(cls):
        return [cls.ACCEPT, cls.PAYMENT_PAID]

    @classmethod
    def make_overdue(cls, status):
        if status.endswith('_OVERDUE'):
            return status
        return status + '_OVERDUE'
