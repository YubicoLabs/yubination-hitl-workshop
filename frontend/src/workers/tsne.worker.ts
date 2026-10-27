import * as tsnejs from 'tsne-js';

self.onmessage = (e) => {
  const { vectors, options, iterations } = e.data;

  const modelOptions = {
    ...options,
    max_iter: iterations,
  };

  const model = new (tsnejs as any).default(modelOptions);

  model.init({ data: vectors });

  // Run the t-SNE algorithm to completion in the worker.
  model.run();

  // Get the solution
  const output = model.getOutput();

  // Send the result back to the main thread
  self.postMessage(output);
};
