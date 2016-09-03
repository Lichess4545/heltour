from django_comments.forms import CommentForm

class CustomForm(CommentForm):
    def __init__(self, *args, **kwargs):
        super(CustomForm, self).__init__(*args, **kwargs)
        self.fields["email"].required = False
