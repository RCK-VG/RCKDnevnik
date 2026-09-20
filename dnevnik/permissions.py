def is_admin(user):
    return user.is_active and (user.is_staff or user.is_superuser)


def can_edit_lesson(user, lesson):
    return is_admin(user) or lesson.teacher_id == user.id


def can_edit_note(user, note):
    return is_admin(user) or note.author_id == user.id


def can_set_justified(user, school_class):
    return is_admin(user) or school_class.homeroom_teacher_id == user.id
