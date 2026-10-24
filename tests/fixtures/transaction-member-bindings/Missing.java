package fixture;
public class Missing {
    static class Result extends MissingSuperclass { Result() {} }
    public void run() { Result r = new Result(); }
}
