aws s3 cp --recursive $1 s3://xcite-simulations/$1 --acl=public-read --exclude=*.egsphsp1 --exclude=*.npz
