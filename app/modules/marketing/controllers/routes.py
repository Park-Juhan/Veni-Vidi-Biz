from app.common.web import bind_module


def create_blueprint(model, title, description, number):
    return bind_module('marketing', model, 'marketing/index.html', title, description, number)
