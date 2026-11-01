from app.common.web import bind_module


def create_blueprint(model, title, description, number):
    return bind_module('cost_optimization', model, 'cost_optimization/index.html', title, description, number)
