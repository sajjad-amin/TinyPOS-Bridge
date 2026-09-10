const path = require('path');

module.exports = {
  apps: [
    {
      name: 'tinypos',
      script: 'main.py',
      interpreter: path.join(__dirname, '.venv', 'bin', 'python3'),
      cwd: __dirname,
      autorestart: true,
      env: {
        NODE_ENV: 'production',
        PYTHONPATH: __dirname,
      },
    },
  ],
};
