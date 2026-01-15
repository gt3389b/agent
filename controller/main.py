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
    import asyncio
    from controller import uds_controller
    from controller import northbound
    
    async def run_controller():
        controller = uds_controller.UdsController(config_file)
        
        # Start northbound API
        nb_api = northbound.ControllerNorthbound(controller)
        
        # Run both controller and northbound API concurrently
        await asyncio.gather(
            controller.start(),
            nb_api.start()
        )
    
    asyncio.run(run_controller())


def main_multi(config_file):
    """Start Multi-MTP controller (UDS + CoAP)"""
    import asyncio
    from controller import multi_mtp_controller
    from controller import northbound
    
    async def run_controller():
        controller = multi_mtp_controller.MultiMtpController(config_file)
        
        # Start northbound API
        nb_api = northbound.ControllerNorthbound(controller)
        
        # Run both controller and northbound API concurrently
        await asyncio.gather(
            controller.start(),
            nb_api.start()
        )
    
    asyncio.run(run_controller())


def main():
    """Main entry point - select controller based on -t flag"""
    parser = argparse.ArgumentParser(description='USP Controller')
    parser.add_argument('-t', '--transport', 
                        choices=['coap', 'uds', 'multi'],
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
    elif args.transport == 'multi':
        main_multi(config_file)
    else:
        logging.error(f"Unsupported transport: {args.transport}")
        return 1
    
    return 0


if __name__ == "__main__":
    main()
