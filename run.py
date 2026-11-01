import argparse
from app.main.application import MODULES, create_app


def port_number(value):
    try:
        port = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError('port must be an integer') from exc
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError('port must be between 1 and 65535')
    return port


if __name__=='__main__':
    parser=argparse.ArgumentParser(description='VENI VIDI BIZ local prototype')
    parser.add_argument('--port',type=port_number,default=5000)
    parser.add_argument('--module',action='append',dest='modules',choices=[item[0] for item in MODULES],help='Enable only a named module; repeat for multiple modules.')
    args=parser.parse_args()
    create_app(enabled_modules=args.modules).run(host='127.0.0.1',port=args.port,debug=False)
