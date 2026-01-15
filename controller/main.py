import logging
import argparse
import asyncio
from controller import controller
from controller import northbound

# logging setup
logging.basicConfig(level=logging.INFO)
logging.getLogger("coap-server").setLevel(logging.DEBUG)


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='USP Controller')
    parser.add_argument('-c', '--config', 
                        default='cfg/controller.json',
                        help='Configuration file path')
    
    args = parser.parse_args()
    
    logging.info("#" * 60)
    logging.info(f"## Starting USP Controller")
    logging.info("#" * 60)
    
    async def run_controller():
        ctrl = controller.Controller(args.config)
        
        # Start northbound API
        nb_api = northbound.ControllerNorthbound(ctrl)
        
        # Run both controller and northbound API concurrently
        await asyncio.gather(
            ctrl.start(),
            nb_api.start()
        )
    
    asyncio.run(run_controller())
    return 0


if __name__ == "__main__":
    main()
