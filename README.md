# agent
A Python implementation of a STOMP Agent (for the USP protocol as defined by the Broadband Forum).

# Build
docker build -t coap-usp-agent .

# Run
docker run -p 15683:15683/udp -itd coap-usp-agent 

# test
coap coap://localhost:15683/.well-known/core
