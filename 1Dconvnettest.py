import numpy as np
import copy
from scipy.io import loadmat, savemat, whosmat

from keras.layers import Input, Dense, Conv1D, MaxPooling1D, Flatten, Activation, add, Dropout, merge
from keras.optimizers import Adam
from keras.layers.normalization import BatchNormalization
from keras.models import Model
from keras import initializers
from keras.engine import Layer, InputSpec
from keras.utils import to_categorical#, plot_model
from keras.callbacks import ModelCheckpoint, TensorBoard, CSVLogger
import os
from keras import backend as K

from sklearn.metrics import log_loss, accuracy_score
import sys
sys.setrecursionlimit(3000)

class Scale(Layer):
    '''Custom Layer for ResNet used for BatchNormalization.
    
    Learns a set of weights and biases used for scaling the input data.
    the output consists simply in an element-wise multiplication of the input
    and a sum of a set of constants:
        out = in * gamma + beta,
    where 'gamma' and 'beta' are the weights and biases larned.
    # Arguments
        axis: integer, axis along which to normalize in mode 0. For instance,
            if your input tensor has shape (samples, channels, rows, cols),
            set axis to 1 to normalize per feature map (channels axis).
        momentum: momentum in the computation of the
            exponential average of the mean and standard deviation
            of the data, for feature-wise normalization.
        weights: Initialization weights.
            List of 2 Numpy arrays, with shapes:
            `[(input_shape,), (input_shape,)]`
        beta_init: name of initialization function for shift parameter
            (see [initializers](../initializers.md)), or alternatively,
            Theano/TensorFlow function to use for weights initialization.
            This parameter is only relevant if you don't pass a `weights` argument.
        gamma_init: name of initialization function for scale parameter (see
            [initializers](../initializers.md)), or alternatively,
            Theano/TensorFlow function to use for weights initialization.
            This parameter is only relevant if you don't pass a `weights` argument.
    '''
    def __init__(self, weights=None, axis=-1, momentum = 0.9, beta_init='zero', gamma_init='one', **kwargs):
        self.momentum = momentum
        self.axis = axis
        self.beta_init = initializers.get(beta_init)
        self.gamma_init = initializers.get(gamma_init)
        self.initial_weights = weights
        super(Scale, self).__init__(**kwargs)

    def build(self, input_shape):
        self.input_spec = [InputSpec(shape=input_shape)]
        shape = (int(input_shape[self.axis]),)

        self.gamma = K.variable(self.gamma_init(shape), name='%s_gamma'%self.name)
        self.beta = K.variable(self.beta_init(shape), name='%s_beta'%self.name)
        self.trainable_weights = [self.gamma, self.beta]

        if self.initial_weights is not None:
            self.set_weights(self.initial_weights)
            del self.initial_weights

    def call(self, x, mask=None):
        input_shape = self.input_spec[0].shape
        broadcast_shape = [1] * len(input_shape)
        broadcast_shape[self.axis] = input_shape[self.axis]

        out = K.reshape(self.gamma, broadcast_shape) * x + K.reshape(self.beta, broadcast_shape)
        return out

    def get_config(self):
        config = {"momentum": self.momentum, "axis": self.axis}
        base_config = super(Scale, self).get_config()
        return dict(list(base_config.items()) + list(config.items()))


def res_subsam(input_tensor,filters,kernel_size,subsam):
	eps= 1.1e-5
	nb_filter1, nb_filter2 = filters
	x = BatchNormalization(epsilon=eps, axis=-1)(input_tensor)
	x = Scale(axis=-1)(x)
	x = Activation('relu')(x)
	x = Dropout(0.25)(x)
	x = Conv1D(filters=nb_filter1,kernel_size=kernel_size,padding='same',use_bias=False)(x) ##
	x = MaxPooling1D(pool_size=subsam)(x)
	x = BatchNormalization(epsilon=eps, axis=-1)(x)
	x = Scale(axis=-1)(x)
	x = Activation('relu')(x)
	x = Dropout(0.25)(x)
	x = Conv1D(filters=nb_filter2,kernel_size=kernel_size,padding='same',use_bias=False)(x) ##	
	short = Conv1D(filters=nb_filter2,kernel_size=kernel_size,padding='same',use_bias=False)(input_tensor)
	short = MaxPooling1D(pool_size=subsam)(short)
	x = add([x,short])
	return x
	
def res_nosub(input_tensor,filters,kernel_size):
	eps= 1.1e-5
	nb_filter1, nb_filter2 = filters
	x = BatchNormalization(epsilon=eps, axis=-1)(input_tensor)
	x = Scale(axis=-1)(x)
	x = Activation('relu')(x)
	x = Dropout(0.25)(x)
	x = Conv1D(filters=nb_filter1,kernel_size=kernel_size,padding='same',use_bias=False)(x) ##
	x = BatchNormalization(epsilon=eps, axis=-1)(x)
	x = Scale(axis=-1)(x)
	x = Activation('relu')(x)
	x = Dropout(0.25)(x)
	x = Conv1D(filters=nb_filter2,kernel_size=kernel_size,padding='same',use_bias=False)(x) ##	
	x = add([x,input_tensor])
	return x
	
def res_first(input_tensor,filters,kernel_size):
	eps=1.1e-5
	nb_filter1, nb_filter2 = filters
	x = Conv1D(filters=nb_filter1,kernel_size=kernel_size,padding='same',use_bias=False)(input_tensor) ##
	x = BatchNormalization(epsilon=eps, axis=-1)(x)
	x = Scale(axis=-1)(x)
	x = Activation('relu')(x)
	x = Dropout(0.25)(x)
	x = Conv1D(filters=nb_filter2,kernel_size=kernel_size,padding='same',use_bias=False)(x) ##	
	x = add([x,input_tensor])
	return x
	
	
def irfanet(eeg_length,num_classes, kernel_size):
	eps = 1.1e-5
	
	EEG_input = Input(shape=(eeg_length,1))
	x = Conv1D(filters=64,kernel_size=kernel_size,padding='same',use_bias=False)(EEG_input) ##
	x = BatchNormalization(epsilon=eps, axis=-1)(x)
	x = Scale(axis=-1)(x)
	x = Activation('relu')(x)
	
	x = res_first(x,filters=[64,64],kernel_size=kernel_size)
	x = res_subsam(x,filters=[64,128],kernel_size=kernel_size,subsam=4)
	x = res_nosub(x,filters=[64,128],kernel_size=kernel_size)
	x = res_subsam(x,filters=[64,256],kernel_size=kernel_size,subsam=4)
	#x = res_nosub(x,filters=[128,128],kernel_size=kernel_size)
	#x = res_subsam(x,filters=[128,128],kernel_size=kernel_size,subsam=2)
	#x = res_nosub(x,filters=[128,128],kernel_size=kernel_size)
	#x = res_subsam(x,filters=[128,192],kernel_size=kernel_size,subsam=2)
	#x = res_nosub(x,filters=[192,192],kernel_size=kernel_size)
	#x = res_subsam(x,filters=[192,192],kernel_size=kernel_size,subsam=2)
	#x = res_nosub(x,filters=[192,192],kernel_size=kernel_size)
	#x = res_subsam(x,filters=[192,256],kernel_size=kernel_size,subsam=2)
	#x = res_nosub(x,filters=[256,256],kernel_size=kernel_size)
	#x = res_subsam(x,filters=[256,256],kernel_size=kernel_size,subsam=2)
	#x = res_nosub(x,filters=[256,256],kernel_size=kernel_size)
	#x = res_subsam(x,filters=[256,512],kernel_size=kernel_size,subsam=2)
	x = BatchNormalization(epsilon=eps, axis=-1)(x)
	x = Scale(axis=-1)(x)
	x = Activation('relu')(x)
	x = Flatten()(x)
	x = Dense(num_classes,activation='softmax')(x)
		
	model = Model(EEG_input, x)
	model.load_weights(filepath='/home/prio/Keras/thesis/irfanet-8/tmp/1DCNN_8917/weights.01-0.8767.hdf5',by_name=False)
	adm = Adam(lr=1e-3, decay=1e-6)
	model.compile(optimizer=adm, loss='categorical_crossentropy', metrics=['accuracy'])
	
	return model

if __name__ == '__main__':
	
	num_classes = 6
	batch_size = 8
	epochs = 3
	file_name = 'eog_rk_new_notrans_234rejects_relabeled.mat'
	eeg_length = 3000
	kernel_size=16
	save_dir = os.path.join(os.getcwd(),'saved_models_keras') #os.getcwd() Return a string representing the current working directory
	model_name = 'keras_1Dconvnet_eog_trained_model.h5'

	
	#use scipy.io to convert .mat to numpy array
	mat_cont = loadmat(file_name)
	X = mat_cont['dat']
	Y = mat_cont['hyp']
	Y=Y-1
	A = np.reshape(X,(47237,3000,1))
	x_test = A[::2,:,:]
	y_test = Y[::2]
	x_train = A[2:X.shape[0]:2,:,:]
	y_train = Y[2:Y.shape[0]:2]
	print('x_train shape:', x_train.shape)
	print(x_train.shape[0], 'train samples')
	print(x_test.shape[0], 'test samples')
	
	y_train = to_categorical(y_train, num_classes)
	y_test = to_categorical(y_test, num_classes)
	print('y_train shape:', y_train.shape)
	
	model = irfanet(eeg_length=eeg_length,num_classes=num_classes, kernel_size=kernel_size)
	#plot_model(model, to_file='model.png', show_shapes=True, show_layer_names=False, rankdir='TB')
	mdlchk=ModelCheckpoint(filepath='/home/prio/Keras/thesis/irfanet-8/tmp/1DCNN_171017/weights.{epoch:02d}-{val_acc:.2f}.hdf5',monitor='val_acc',save_best_only=True,mode='max')
	tensbd=TensorBoard(log_dir='./logs',batch_size=batch_size)
	csv_logger = CSVLogger('training.log',separator=',', append=True )

	model.fit(x_train,y_train,
	 batch_size=batch_size,
	 epochs=epochs,
	 shuffle=True,
	 verbose=1,
	 validation_data=(x_test,y_test),
	 callbacks=[mdlchk,tensbd,csv_logger],
	 )
	 
	pred= model.predict(x_test,batch_size=batch_size, verbose=1)
	print(pred)
	
	score = log_loss(y_test,pred)
	score_ = accuracy_score(y_test,pred)
	print(score)
	print(score_)
	
	if not os.path.isdir(save_dir):
		os.makedirs(save_dir)
	model_path = os.path.join(save_dir, model_name)
	model.save(model_path)
	print('Saved trained model at %s ' % model_path)
	
	
		
	
