-- Migration number: 0005  クレジットカード払いの経費を支払先なしでも登録できるよう、未払金の取引先必須を外す
UPDATE accounts SET requires_counterparty = 0 WHERE code = '200';
