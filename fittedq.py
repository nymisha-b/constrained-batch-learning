
from fitted_algo import FittedAlgo
import numpy as np
from tqdm import tqdm
from env_nn import *
from keras import backend as K
from keras.callbacks import EarlyStopping, ModelCheckpoint, ReduceLROnPlateau
from operator import add 


class PortfolioFittedQIteration(FittedAlgo):
    def __init__(self, state_space_dim, 
                       action_space_dim, 
                       max_epochs, 
                       gamma, 
                       model_type='cnn', 
                       num_frame_stack=None,
                       initialization=None,
                       freeze_cnn_layers=False):
        '''
        An implementation of fitted Q iteration

        num_inputs: number of inputs
        action_space_dim: dimension of action space
        max_epochs: positive int, specifies how many iterations to run the algorithm
        gamma: discount factor
        '''
        self.initialization = initialization
        self.freeze_cnn_layers = freeze_cnn_layers
        self.model_type = model_type
        self.state_space_dim = state_space_dim
        self.action_space_dim = action_space_dim
        self.max_epochs = max_epochs
        self.gamma = gamma
        self.num_frame_stack = num_frame_stack
        self.Q_k = None
        self.Q_k_minus_1 = None

        earlyStopping = EarlyStopping(monitor='val_loss', min_delta=1e-4,  patience=10, verbose=1, mode='min', restore_best_weights=True)
        mcp_save = ModelCheckpoint('fqi.hdf5', save_best_only=True, monitor='val_loss', mode='min')
        reduce_lr_loss = ReduceLROnPlateau(monitor='val_loss', factor=0.1, patience=7, verbose=1, min_delta=1e-4, mode='min')

        self.more_callbacks = [earlyStopping, mcp_save, reduce_lr_loss]

        super().__init__()


    def run(self, dataset, epochs=1, epsilon=1e-8, desc='FQI', exact=None, **kw):
        # dataset is the original dataset generated by pi_{old} to which we will find
        # an approximately optimal Q

        # if self.Q_k is None:
        self.Q_k = self.init_Q(**kw)
#        print(type(dataset['next_states'][0]),dataset['next_states'][0].shape,len(dataset['next_states']))
        x_prime = np.array(dataset['next_states'])
#        x_prime = np.rollaxis(x_prime, 1,4)
#        self.Q_k.min_over_a([x_prime], x_preprocessed=True)[0]
#        self.Q_k_minus_1.min_over_a([x_prime], x_preprocessed=True)[0]
#        self.Q_k.copy_over_to(self.Q_k_minus_1)
        values = []
        lr=self.Q_k.lr
        for k in tqdm(range(self.max_epochs), desc=desc):
#        for k in range(self.max_epochs):
            print("epoch:",k)
            batch_size = 256
            
            dataset_length = len(dataset)
#            print("dataset length: ",dataset_length)
            perm = np.random.permutation(range(dataset_length))
            eighty_percent_of_set = int(1.*len(perm))
            training_idxs = perm[:eighty_percent_of_set]
            validation_idxs = perm[eighty_percent_of_set:]
            training_steps_per_epoch = int(np.ceil(len(training_idxs)/float(batch_size)))
            validation_steps_per_epoch = int(np.ceil(len(validation_idxs)/float(batch_size)))
            # steps_per_epoch = 1 #int(np.ceil(len(dataset)/float(batch_size)))
#            print("pre")
            train_gen = self.generator(dataset, training_idxs, fixed_permutation=True, batch_size=batch_size)
#            print("post",len(train_gen),dataset_length)
            # val_gen = self.generator(dataset, validation_idxs, fixed_permutation=True, batch_size=batch_size)
#            if (k >= (self.max_epochs-10)): K.set_value(self.Q_k.optimizer.lr, 0.0001)
            if (k >= (self.max_epochs-10)): lr= 0.0001
#            print("generator",train_gen)
            self.fit_generator(train_gen, 
                               model_params = self.Q_k.parameters(),
                               lr=lr,
                               steps_per_epoch=training_steps_per_epoch,
                               #validation_data=val_gen, 
                               #validation_steps=validation_steps_per_epoch,
                               epochs=epochs, 
                               evaluate=False, 
                               tqdm_verbose=0,
                               additional_callbacks = self.more_callbacks)
#            self.Q_k.copy_over_to(self.Q_k_minus_1)
#            if k >= (self.max_epochs-10):
            if k<5:
                c,g,perf = exact.run(self.Q_k,to_monitor=k==self.max_epochs)
                values.append([c,perf])
                
        return self.Q_k, values

#    @threadsafe_generator
    def generator(self, dataset, training_idxs, fixed_permutation=False,  batch_size = 64):
#        data_wcost=[]
        data_length = len(training_idxs)
#        print("data_length" ,data_length )
        steps = int(np.ceil(data_length/float(batch_size)))
        i = -1
        amount_of_data_calcd = 0
        if fixed_permutation:
            calcd_costs = np.empty((len(training_idxs),), dtype='float64')
        while i<steps-1:
#            print(steps,i)
            i = (i + 1) % steps
#            print('Getting batch: %s to %s' % ((i*batch_size),((i+1)*batch_size)))
            if fixed_permutation:
                if i == 0: perm = np.random.permutation(training_idxs)
                batch_idxs = perm[(i*batch_size):((i+1)*batch_size)]
            else:
                batch_idxs = np.random.choice(training_idxs, batch_size)
            # amount_of_data_calcd += len(batch_idxs)
            # import pdb; pdb.set_trace()  
#            print(dataset['cost'])
#            X = np.rollaxis(dataset['prev_states'][batch_idxs],1,4)
            X=[dataset['prev_states'][i] for i in batch_idxs]
            actions = [np.atleast_2d(dataset['a'][i]).T for i in batch_idxs]
#            x_prime = np.rollaxis(dataset['next_states'][batch_idxs],1,4)
            x_prime = [dataset['next_states'][i] for i in batch_idxs]
            dataset_costs = [dataset['cost'][i] for i in batch_idxs]
            dones = [dataset['done'][i] for i in batch_idxs]

            # if fixed_permutation:
            #     if amount_of_data_calcd <= data_length:
            #         costs = dataset_costs + self.gamma*self.Q_k_minus_1.min_over_a([x_prime], x_preprocessed=True)[0]*(1-dones.astype(int))
            #         calcd_costs[(i*batch_size):((i+1)*batch_size)] = costs
            #     else:
            #         costs = calcd_costs[(i*batch_size):((i+1)*batch_size)]
            # else:
#            print(len(dataset_costs),batch_idxs.shape)
            Q_min,_ = self.Q_k.min_over_a_cont(x_prime)
#            print(len([self.gamma*Q*(1-int(x)) for Q,x in zip(Q_min,dones)]),len(dataset_costs))
            costs = list(map(add, dataset_costs, [self.gamma*Q*(1-int(x)) for Q,x in zip(Q_min,dones)]))
#            print(type(costs),len(costs),len(X[1]))
#            X = self.Q_k_minus_1.representation([X], actions, x_preprocessed=True)
#            data_wcost.append((X,actions, costs))
            yield (X,actions, costs)

    def init_Q(self, epsilon=1e-10, **kw):
#        print(self.state_space_dim, self.action_space_dim)
        model = PortfolioNN_model(self.state_space_dim, self.action_space_dim,n_epochs=10,**kw)
        if (self.initialization is not None) and self.freeze_cnn_layers:
            self.initialization.Q.copy_over_to(model)
            for layer in model.model.layers:
                if layer.trainable: 
                    try:
                        layer.kernel.initializer.run( session = K.get_session() )
                    except:
                        pass
                    try:
                        layer.bias.initializer.run( session = K.get_session() )
                    except:
                        pass
        return model
