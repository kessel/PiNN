FROM tensorflow/tensorflow:1.15.2-py3-jupyter

# Install PiNN
COPY . /opt/src/pinn
RUN ls /opt/src/pinn
RUN pip install /opt/src/pinn && \
    pip install -r /opt/src/pinn/requirements-dev.txt && \
    pip install -r /opt/src/pinn/requirements-extra.txt && \
    jupyter nbextension enable widgetsnbextension --py --sys-prefix && \
    jupyter nbextension enable nglview --py --sys-prefix && \
    jupyter tensorboard enable --sys-prefix 

# Setup
ENTRYPOINT ["pinn_train"]
