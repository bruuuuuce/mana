package fixture;
public class Ambiguous {
    static class Result {
        Result(String x) {}
        Result(Integer x) {}
    }
    public void run() { Result r = new Result(null); }
}
