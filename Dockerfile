FROM ubuntu:16.04

RUN echo "root:Docker!" | chpasswd

RUN apt-get -y update 
RUN apt-get -y upgrade

RUN apt-get install -y git
RUN apt-get install -y sudo
RUN apt-get install -y python
RUN apt-get install -y python3
RUN apt-get install -y python-pip
RUN apt-get install -y python3-pip
RUN apt-get install -y vim
RUN apt-get install -y curl
RUN apt-get install -y unzip
RUN apt-get install -y npm

RUN mkdir /tmp/protoc && \
	 cd /tmp/protoc && \

	# Make sure you grab the latest version
	curl -OL https://github.com/google/protobuf/releases/download/v3.2.0/protoc-3.2.0-linux-x86_64.zip && \

	# Unzip
	unzip protoc-3.2.0-linux-x86_64.zip -d protoc3 && \

	# Move protoc to /usr/local/bin/
	sudo mv protoc3/bin/* /usr/local/bin/ && \

	# Move protoc3/include to /usr/local/include/
	sudo mv protoc3/include/* /usr/local/include/ && \

	# Optional: change owner
	#sudo chown [user] /usr/local/bin/protoc && \
	#sudo chown -R [user] /usr/local/include/google && \

	ln -s /protoc3/bin/protoc /usr/bin/protoc 

RUN npm install -g coap-cli
RUN ln -s "$(which nodejs)" /usr/bin/node

#RUN useradd -ms /bin/bash skates 
#USER skates

COPY . /app
WORKDIR /app
RUN pip3 install --upgrade pip
RUN make init
RUN make schema
EXPOSE 15683
CMD ["make","runcoap"]
