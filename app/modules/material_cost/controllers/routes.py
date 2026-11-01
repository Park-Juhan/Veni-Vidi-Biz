from app.common.web import bind_module


def create_blueprint(model, title, description, number):
    return bind_module('material_cost', model, 'material_cost/index.html', title, description, number)
