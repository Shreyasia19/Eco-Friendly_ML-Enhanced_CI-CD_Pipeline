import numpy as np
import random

def evaluate_cicd(config):
    cpu, mem, rep, par = config

    # Dummy scoring (replace later)
    build_time = (500 / cpu) + (mem / 500) + (rep * 1.5)
    resource_penalty = (cpu * 2) + (mem / 800)

    return build_time + resource_penalty


bounds = [
    (0.1, 2.0),     # CPU cores
    (256, 4096),    # Memory MB
    (1, 10),        # Replicas
    (1, 5),         # Parallel jobs
]


def differential_evolution(bounds, max_iter=30, pop_size=15, F=0.8, CR=0.7):
    dim = len(bounds)
    population = []

    for _ in range(pop_size):
        ind = [random.uniform(bounds[i][0], bounds[i][1]) for i in range(dim)]
        population.append(ind)

    fitness = [evaluate_cicd(ind) for ind in population]

    for iteration in range(max_iter):
        for i in range(pop_size):

            candidates = list(range(pop_size))
            candidates.remove(i)
            a, b, c = random.sample(candidates, 3)

            x1, x2, x3 = population[a], population[b], population[c]

            mutant = [
                x1[j] + F * (x2[j] - x3[j])
                for j in range(dim)
            ]

            for j in range(dim):
                mutant[j] = np.clip(mutant[j], bounds[j][0], bounds[j][1])

            trial = []
            R = random.randint(0, dim - 1)
            for j in range(dim):
                if random.random() < CR or j == R:
                    trial.append(mutant[j])
                else:
                    trial.append(population[i][j])

            # integer parameters
            trial[2] = int(round(trial[2]))
            trial[3] = int(round(trial[3]))

            trial_fitness = evaluate_cicd(trial)

            if trial_fitness < fitness[i]:
                population[i] = trial
                fitness[i] = trial_fitness

        print(f"Iteration {iteration+1}/{max_iter}, Best = {min(fitness):.4f}")

    best_index = np.argmin(fitness)
    return population[best_index], fitness[best_index]


if __name__ == "__main__":
    best_config, best_score = differential_evolution(bounds)
    print("Best config:", best_config)
    print("Best score:", best_score)
