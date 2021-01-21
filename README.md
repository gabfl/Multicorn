[![Build Status](https://travis-ci.org/gabfl/Multicorn.svg?branch=master)](https://travis-ci.org/gabfl/Multicorn)

# gabfl/Multicorn

Multicorn Python Wrapper for Postgresql 9.2+ Foreign Data Wrapper. The original project is [Segfault-Inc/Multicorn](https://github.com/Segfault-Inc/Multicorn).

The Multicorn Foreign Data Wrapper allows you to fetch foreign data in Python in your PostgreSQL server.

## Differences with the original project

 - Default build to python3, remove support for Python2

## How to build gabfl/Multicorn

```bash
apt-get update
apt-get install --yes postgresql-server-dev-12 python3-dev make gcc git

git clone git://github.com/gabfl/Multicorn.git && cd Multicorn
make && make install
```

## License

Multicorn is distributed under the [PostgreSQL license](./LICENSE).