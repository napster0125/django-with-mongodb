from djangotoolbox.fields import ListField, SetField, DictField

class A(object):

    def __init__(self, op, value):
        self.op = op
        self.val = value

    def as_q(self, field):
        if isinstance(field, (DictField, ListField, SetField)):
            return "%s.%s" % (field.name, self.op), self.val
