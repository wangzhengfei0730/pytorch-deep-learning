import numpy as np
import torch
import torch.nn as nn
from torch.optim import Adam
from memory import ReplayBuffer
from model import Actor, Critic
from utils import OrnsteinUhlenbeckProcess
from utils import to_numpy, to_tensor, soft_update, hard_update

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")


class DDPG(object):
    def __init__(self, nb_states, nb_actions, args):
        self.nb_states = nb_states
        self.nb_actions = nb_actions
        self.discrete = args.discrete

        net_config = {
            'hidden1' : args.hidden1,
            'hidden2' : args.hidden2
        }

        # Actor and Critic initialization
        self.actor = Actor(self.nb_states, self.nb_actions, **net_config)
        self.actor_target = Actor(self.nb_states, self.nb_actions, **net_config)
        self.actor_optim = Adam(self.actor.parameters(), lr=args.actor_lr)

        self.critic = Critic(self.nb_states, self.nb_actions, **net_config)
        self.critic_target = Critic(self.nb_states, self.nb_actions, **net_config)
        self.critic_optim = Adam(self.critic.parameters(), lr=args.critic_lr, weight_decay=args.weight_decay)

        hard_update(self.critic_target, self.critic)
        hard_update(self.actor_target, self.actor)

        # Replay Buffer and noise
        self.memory = ReplayBuffer(args.memory_size)
        self.noise = OrnsteinUhlenbeckProcess(mu=np.zeros(nb_actions), sigma=float(0.2) * np.ones(nb_actions))

        self.last_state = None
        self.last_action = None

        # Hyper parameters
        self.batch_size = args.batch_size
        self.tau = args.tau
        self.discount = args.discount
        self.epsilon = 1.
        self.epsilon_decay = 1. / args.epsilon_decay

        # CUDA
        self.use_cuda = args.cuda
        if self.use_cuda:
            self.cuda()

    def cuda(self):
        self.actor.to(device)
        self.actor_target.to(device)
        self.critic.to(device)
        self.critic_target.to(device)

    def eval(self):
        self.actor.eval()
        self.actor_target.eval()
        self.critic.eval()
        self.critic_target.eval()

    def train(self):
        self.actor.train()
        self.actor_target.train()
        self.critic.train()
        self.critic_target.train()

    def reset(self, obs):
        self.last_state = obs
        self.noise.reset()

    def observe(self, reward, state, done):
        self.memory.append([self.last_state, self.last_action, reward, state, done])
        self.last_state = state

    def random_action(self):
        action = np.random.uniform(-1., 1., self.nb_actions)
        self.last_action = action
        return action.argmax() if self.discrete else action

    def select_action(self, state, exploration_noise=0, exploration_decay=True):
        self.eval()
        action = to_numpy(self.actor(to_tensor(np.array([state]), device=device))).squeeze(0)
        self.train()
        exploration_noise = exploration_noise * max(self.epsilon, 0)
        if exploration_decay:
            self.epsilon -= self.epsilon_decay
        action = action * (1 - exploration_noise) + self.noise.sample() * exploration_noise
        action = np.clip(action, -1., 1.)
        self.last_action = action
        return action.argmax() if self.discrete else action

    def update_policy(self):
        state_batch, action_batch, reward_batch, next_state_batch, terminal_batch = self.memory.sample_batch(self.batch_size)

        # compute target Q value
        next_q_values = self.critic_target([
            to_tensor(next_state_batch, device=device),
            self.actor_target(to_tensor(next_state_batch, device=device))
        ])
        target_q_batch = to_tensor(reward_batch, device=device) + \
                         self.discount * to_tensor((1 - terminal_batch.astype(np.float)), device=device) * next_q_values

        # Critic and Actor update
        self.critic.zero_grad()
        q_batch = self.critic([to_tensor(state_batch, device=device), to_tensor(action_batch, device=device)])
        critic_loss = nn.MSELoss()(q_batch, target_q_batch.detach())
        critic_loss.backward()
        self.critic_optim.step()

        self.actor.zero_grad()
        actor_loss = -self.critic([
            to_tensor(state_batch, device=device),
            self.actor(to_tensor(state_batch, device=device))
        ]).mean()
        actor_loss.backward()
        self.actor_optim.step()

        # Target update
        soft_update(self.actor_target, self.actor, self.tau)
        soft_update(self.critic_target, self.critic, self.tau)

        return -actor_loss, critic_loss

    def save_model(self, output, num=1):
        if self.use_cuda:
            self.actor.to(torch.device("cpu"))
            self.critic.to(torch.device("cpu"))
        torch.save(
            self.actor.state_dict(),
            '{}/actor{}.pkl'.format(output, num)
        )
        torch.save(
            self.critic.state_dict(),
            '{}/critic{}.pkl'.format(output, num)
        )
        if self.use_cuda:
            self.actor.to(device)
            self.critic.to(device)

    def load_model(self, output, num=1):
        self.actor.load_state_dict(
            torch.load('{}/actor{}.pkl'.format(output, num))
        )
        self.actor_target.load_state_dict(
            torch.load('{}/actor{}.pkl'.format(output, num))
        )
        self.critic.load_state_dict(
            torch.load('{}/critic{}.pkl'.format(output, num))
        )
        self.critic_target.load_state_dict(
            torch.load('{}/critic{}.pkl'.format(output, num))
        )
        if self.use_cuda:
            self.cuda()
