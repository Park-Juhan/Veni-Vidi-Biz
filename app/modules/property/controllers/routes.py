from app.common.web import bind_module


def create_blueprint(model, title, description, number):
    # The long location form is entered step by step.
    return bind_module('property', model, 'property/index.html', title, description, number, wizard=True)
