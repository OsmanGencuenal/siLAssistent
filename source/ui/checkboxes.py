"""Shared checkbox behavior for highlighted selection areas."""
class Checkboxes:
    @classmethod
    def full_click(cls,checkbox):
        # Include the styled padding and unused width in Qt's native hit test.
        checkbox.hitButton=lambda position:checkbox.rect().contains(position)
        return checkbox
