import logging
import argparse

# logging setup
logging.basicConfig(level=logging.INFO)
logging.getLogger("coap-server").setLevel(logging.DEBUG)


def main_coap(config_file):
    """Start CoAP controller"""
    from controller import coap_controller
    
    controller = coap_controller.CoapController(config_file)
    controller.start()


def main_uds(config_file):
    """Start UDS controller"""
    from controller import uds_controller
    
    controller = uds_controller.UdsController(config_file)
    controller.start()


def main():
    """Main entry point - select controller based on -t flag"""
    parser = argparse.ArgumentParser(description='USP Controller')
    parser.add_argument('-t', '--transport', 
                        choices=['coap', 'uds'],
                        default='coap',
                        help='Transport protocol to use')
    
    args = parser.parse_args()
    
    logging.info("#" * 60)
    logging.info(f"## Starting USP Controller - Transport: {args.transport.upper()}")
    logging.info("#" * 60)
    
    config_file = f'cfg/{args.transport}-controller.json'
    
    if args.transport == 'uds':
        main_uds(config_file)
    elif args.transport == 'coap':
        main_coap(config_file)
    else:
        logging.error(f"Unsupported transport: {args.transport}")
        return 1
    
    return 0


if __name__ == "__main__":
    main()
