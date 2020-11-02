FROM quay.io/azavea/raster-vision:pytorch-1190b35

RUN pip3 install --upgrade pystac==0.5.2 && apt-get install -y nano

# Pipelines
COPY sen1floods11_pipeline.py /workdir/
COPY usfimr_vector_pipeline.py /workdir/
COPY usfimr_raster_pipeline.py /workdir/
COPY usfimr_inference_pipeline.py /workdir/
COPY default /root/.rastervision/

# Patches
COPY patches/label.diff /tmp/
RUN cd /opt/src && \
    patch -p1 < /tmp/label.diff

CMD ["bash"]
