# Copyright 2019 Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

FROM ubuntu:16.04

# Installing software-properties-common to get test PPA
# Installing gcc/g++ version 5 via a test PPA to build cbmc on Ubuntu 14
# Installing default-jdk to get javacc to build cbmc (java component)
# Installing emacs24-bin-common to get etags (try etags with ctags pkg)
# Installing bc for Annapurna stage1 Makefile

ENV DEBIAN_FRONTEND noninteractive
ARG UBUNTU_ARCHIVE
ENV UBUNTU_ARCHIVE ${UBUNTU_ARCHIVE:-archive.ubuntu.com}

RUN sed -i "s#/archive.ubuntu.com#/${UBUNTU_ARCHIVE}#g" \
    /etc/apt/sources.list

RUN apt-get -y update && \
    apt-get -y upgrade && \
    apt-get -y install --no-install-recommends \
    bc \
    emacs24-bin-common \
    gcc \
    git \
    libc6-dev-i386 \
    make \
    patch \
    python \
    python-future \
    python-pip \
    python-setuptools \
    python3 \
    python3-future \
    python3-pip \
    python3-setuptools \
    wget

# install libssl-dev for encryption SDK
# install cmake, openssl, libssl-dev for MQTT
RUN apt-get -y install --no-install-recommends cmake openssl libssl-dev

# Install the latest version of pip; however, do not use pip install --upgrade pip here
# Install awscli and boto3 with pip and not apt-get (want python 2.7 version)
RUN pip install --upgrade awscli && \
    pip install --upgrade boto3 && \
    pip3 install --upgrade awscli && \
    pip3 install --upgrade boto3

RUN apt-get -y --purge remove \
    python-pip \
    python-setuptools \
    python3-pip \
    python3-setuptools \
    && apt-get -y autoremove && apt-get clean

RUN apt-get -y install locales

RUN sed -i -e 's/# en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen && \
    locale-gen
ENV LANG en_US.UTF-8
ENV LANGUAGE en_US:en
ENV LC_ALL en_US.UTF-8

ADD bin /cbmc-batch-boot

ENV PATH "$PATH:/cbmc"
ENV PATH "$PATH:/cbmc-viewer"
ENV PATH "$PATH:/cbmc-batch"

ENTRYPOINT ["python", "/cbmc-batch-boot/boot.py"]


